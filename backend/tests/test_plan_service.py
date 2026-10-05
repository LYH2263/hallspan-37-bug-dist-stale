import json

import pytest

from app.models.models import Hall, SeatPlan
from app.services import plan_service
from app.services.seed import seed_if_empty
from app.services.seat_engine import manhattan


def _min_pair_dist(result: dict) -> int:
    assigns = result["assignments"]
    best = None
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a["row"], a["col"]), (b["row"], b["col"]))
            best = d if best is None else min(best, d)
    return best if best is not None else 10**9


def _plan_at(db, hall_id, dist):
    hall = db.get(Hall, hall_id)
    hall.min_manhattan = dist
    plan = plan_service.generate_plan(db, hall)
    db.commit()
    return plan


# ---------- 越界拒绝：三处不动 ----------

@pytest.mark.parametrize("bad", [0, -1, 10, 99])
def test_reject_out_of_range_changes_nothing(db, hall_with_candidates, bad):
    hall = hall_with_candidates
    plan = _plan_at(db, hall.id, 2)
    before_json = plan.result_json
    plan_count = db.query(SeatPlan).count()

    with pytest.raises(ValueError):
        plan_service.update_min_manhattan(db, hall.id, bad)

    db.refresh(hall)
    db.refresh(plan)
    assert hall.min_manhattan == 2                # 距离数字不动
    assert plan.min_manhattan == 2                # 最新方案距离不动
    assert plan.result_json == before_json        # 排座图/违规/统计不动
    assert db.query(SeatPlan).count() == plan_count  # 不新增方案行


def test_diagonal_boundary_accepted(db, hall_with_candidates):
    # 5x6 对角线 = 9，恰好等于上限允许保存
    hall, plan = plan_service.update_min_manhattan(db, hall_with_candidates.id, 9)
    assert hall.min_manhattan == 9
    assert plan.min_manhattan == 9


# ---------- 2 -> 3：最新图不再保留距离为 2 的邻对 ----------

def test_change_2_to_3_rewrites_latest(db, hall_with_candidates):
    hall = hall_with_candidates
    plan = _plan_at(db, hall.id, 2)
    assert _min_pair_dist(json.loads(plan.result_json)) == 2  # 旧图确有距离 2 的邻对

    hall, plan = plan_service.update_min_manhattan(db, hall.id, 3)

    assert hall.min_manhattan == 3
    assert plan.min_manhattan == 3
    result = json.loads(plan.result_json)
    assert result["min_manhattan"] == 3
    assert result["hall"]["min_manhattan"] == 3
    assert _min_pair_dist(result) >= 3            # 不再有距离 < 3（含距离 2）的邻对
    # 违规与统计按新距离对齐
    assert not any(v["kind"] == "distance" for v in result["violations"])
    assert result["stats"]["violations"] == len(result["violations"])


# ---------- 历史方案钉死，改距只动最新 ----------

def test_history_plans_pinned_on_distance_change(db, hall_with_candidates):
    hall = hall_with_candidates
    older = _plan_at(db, hall.id, 2)
    latest = _plan_at(db, hall.id, 2)
    assert latest.id > older.id
    older_snapshot = older.result_json

    plan_service.update_min_manhattan(db, hall.id, 3)

    db.refresh(older)
    db.refresh(latest)
    assert older.min_manhattan == 2               # 历史距离钉死
    assert older.result_json == older_snapshot    # 历史图/违规/统计不回刷
    assert _min_pair_dist(json.loads(older.result_json)) == 2
    assert latest.min_manhattan == 3              # 只有最新一条被重写
    assert _min_pair_dist(json.loads(latest.result_json)) >= 3
    assert db.query(SeatPlan).count() == 2        # 不新增、不删除历史行


# ---------- 故意制造失败：距离与图一并回滚 ----------

def test_failure_rolls_back_distance_and_plan(db, hall_with_candidates, monkeypatch):
    hall = hall_with_candidates
    plan = _plan_at(db, hall.id, 2)
    before_json = plan.result_json
    plan_count = db.query(SeatPlan).count()

    def boom(*a, **k):
        raise RuntimeError("排座引擎故意失败")

    monkeypatch.setattr(plan_service, "build_plan", boom)

    with pytest.raises(RuntimeError):
        plan_service.update_min_manhattan(db, hall.id, 3)

    db.expire_all()
    hall = db.get(Hall, hall.id)
    plan = db.query(SeatPlan).order_by(SeatPlan.id.desc()).first()
    assert hall.min_manhattan == 2                # 距离数字回到保存前
    assert plan.min_manhattan == 2                # 图回到保存前
    assert plan.result_json == before_json
    assert db.query(SeatPlan).count() == plan_count


def test_missing_hall_raises(db):
    with pytest.raises(LookupError):
        plan_service.update_min_manhattan(db, 999, 3)


# ---------- 种子：最小距 3 ----------

def test_seed_uses_min_dist_3(db):
    seed_if_empty(db)
    hall = db.query(Hall).one()
    assert hall.min_manhattan == 3
    latest = plan_service.latest_plan(db, hall.id)
    assert latest is not None
    assert latest.min_manhattan == 3
    assert _min_pair_dist(json.loads(latest.result_json)) >= 3  # 不存在距离为 2 的邻对
