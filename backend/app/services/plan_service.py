"""改距联动重排。

关键约束：
- 保存新最小距离时，必须与最新方案在同一事务内一起落地；任一步失败，
  距离数字与方案内容全部回到保存前。
- 历史方案钉死生成时的距离结果，改距只重写最新方案，绝不回刷历史。
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import find_violations, place_candidates, plan_to_dict


def hall_diagonal(hall: Hall) -> int:
    """网格两点间最大曼哈顿距离：对角两个角 (rows-1)+(cols-1)。"""
    return hall.rows + hall.cols - 2


def validate_min_dist(hall: Hall, min_dist: int) -> None:
    """距离 < 1 或 > 考室对角线则拒绝（三处不动：不提交任何变更）。"""
    if not isinstance(min_dist, int) or isinstance(min_dist, bool):
        raise ValueError("最小曼哈顿距离必须为整数")
    if min_dist < 1:
        raise ValueError("最小曼哈顿距离不得小于 1")
    diagonal = hall_diagonal(hall)
    if min_dist > diagonal:
        raise ValueError(f"最小曼哈顿距离不得超过考室对角线 {diagonal}")


def load_candidates(db: Session, hall_id: int) -> list[dict]:
    return [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall_id)).all()
    ]


def build_plan(hall: Hall, cands: list[dict], min_dist: int) -> dict:
    """按给定距离生成完整方案：排座图、违规、统计全部对齐同一距离。"""
    assigns, unplaced = place_candidates(hall.rows, hall.cols, min_dist, cands)
    viols = find_violations(hall.rows, hall.cols, min_dist, assigns)
    result = plan_to_dict(assigns, unplaced, viols, hall.rows, hall.cols)
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": min_dist}
    result["min_manhattan"] = min_dist
    return result


def generate_plan(db: Session, hall: Hall) -> SeatPlan:
    """以考室当前距离生成一条全新方案（用于重排/无历史时的兜底）。"""
    cands = load_candidates(db, hall.id)
    result = build_plan(hall, cands, hall.min_manhattan)
    plan = SeatPlan(
        hall_id=hall.id,
        created_at=datetime.utcnow(),
        min_manhattan=hall.min_manhattan,
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(plan)
    return plan


def latest_plan(db: Session, hall_id: int) -> SeatPlan | None:
    return db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())
    ).first()


def update_min_manhattan(db: Session, hall_id: int, new_dist: int) -> tuple[Hall, SeatPlan]:
    """改距主入口：校验 → 同事务改写距离 + 最新方案。

    - 校验失败：抛 ValueError，不产生任何写入。
    - 重排或提交失败：整个事务回滚，距离与图一并回到保存前。
    - 历史方案行（除最新一条外）一律不触碰。
    """
    hall = db.get(Hall, hall_id)
    if hall is None:
        raise LookupError("考室不存在")
    validate_min_dist(hall, new_dist)

    old_dist = hall.min_manhattan
    # 距离未变也不重写（幂等：无最新方案时仍补建）。
    plan = latest_plan(db, hall_id)
    if plan is not None and old_dist == new_dist:
        return hall, plan

    try:
        hall.min_manhattan = new_dist
        cands = load_candidates(db, hall_id)
        result = build_plan(hall, cands, new_dist)
        payload = json.dumps(result, ensure_ascii=False)

        if plan is None:
            plan = SeatPlan(
                hall_id=hall_id,
                created_at=datetime.utcnow(),
                min_manhattan=new_dist,
                result_json=payload,
            )
            db.add(plan)
        else:
            # 只重写最新一条；历史方案钉死生成时的距离与结果，绝不回刷
            plan.min_manhattan = new_dist
            plan.result_json = payload

        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(hall)
    db.refresh(plan)
    return hall, plan
