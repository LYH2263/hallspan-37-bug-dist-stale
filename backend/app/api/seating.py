import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Hall
from app.services import plan_service

router = APIRouter(prefix="/seating", tags=["seating"])


def _serialize(plan) -> dict:
    data = json.loads(plan.result_json)
    return {"id": plan.id, "plan_min_manhattan": plan.min_manhattan, **data}


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    """以考室当前距离生成一条新方案；方案钉死本次生成时的距离。"""
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    try:
        plan = plan_service.generate_plan(db, hall)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    return _serialize(plan)


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    plan = plan_service.latest_plan(db, hall_id)
    if not plan:
        hall = db.get(Hall, hall_id)
        if not hall:
            raise HTTPException(404, "考室不存在")
        try:
            plan = plan_service.generate_plan(db, hall)
            db.commit()
        except Exception:
            db.rollback()
            raise
        db.refresh(plan)
    return _serialize(plan)


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    """违规清单与最新方案同源：方案钉死生成时的距离，清单原样返回。"""
    data = latest(hall_id=hall_id, db=db)
    return {
        "hall_id": hall_id,
        "violations": data.get("violations", []),
        "unplaced": data.get("unplaced", []),
    }


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    """人数统计与最新方案同源：seated/unplaced/violations/capacity 原样返回。"""
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
