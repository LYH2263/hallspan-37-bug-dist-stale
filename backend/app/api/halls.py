from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Hall
from app.services.plan_service import update_min_manhattan

router = APIRouter(prefix="/halls", tags=["halls"])


class HallDistanceUpdate(BaseModel):
    min_manhattan: int


def _serialize(r: Hall) -> dict:
    return {"id": r.id, "code": r.code, "name": r.name, "rows": r.rows, "cols": r.cols,
            "min_manhattan": r.min_manhattan}


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [_serialize(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


@router.patch("/{hall_id}")
@router.put("/{hall_id}")
def update_hall(hall_id: int, body: HallDistanceUpdate, db: Session = Depends(get_db)):
    """保存新最小距离：同事务重写最新方案；越界或失败则距离与图一并回滚。"""
    try:
        hall, plan = update_min_manhattan(db, hall_id, body.min_manhattan)
    except LookupError:
        raise HTTPException(404, "考室不存在")
    except ValueError as e:
        # 三处不动：距离、排座图、历史方案均不改变
        raise HTTPException(422, str(e))
    return {**_serialize(hall), "latest_plan_id": plan.id}
