import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet, SeatPlan
from app.services import plan_service


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    hall = Hall(code="H101", name="一号考室", rows=5, cols=6, min_manhattan=2)
    db.add(hall); db.flush()
    p = PaperSet(code="P-A", title="A"); db.add(p); db.flush()
    for i in range(12):
        db.add(Candidate(hall_id=hall.id, name=f"考生{i}", ticket_no=f"T{i}", paper_id=p.id))
    db.commit()

    def override_get_db():
        # 每个请求用独立 session，但共享同一内存库（StaticPool 单连接）
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestSession
    app.dependency_overrides.clear()


def _latest_json(Session):
    s = Session()
    plan = s.query(SeatPlan).order_by(SeatPlan.id.desc()).first()
    s.close()
    return plan


def test_patch_rejects_below_one_and_above_diagonal(client):
    c, Session = client
    for bad in (0, -5, 10):
        r = c.patch("/api/halls/1", json={"min_manhattan": bad})
        assert r.status_code == 422
    s = Session()
    assert s.get(Hall, 1).min_manhattan == 2
    s.close()


def test_patch_rewrites_latest_plan_atomically(client):
    c, Session = client
    # 先有一条距离 2 的方案
    s = Session()
    h = s.get(Hall, 1)
    plan_service.generate_plan(s, h)
    s.commit(); s.close()

    r = c.patch("/api/halls/1", json={"min_manhattan": 3})
    assert r.status_code == 200
    assert r.json()["min_manhattan"] == 3

    plan = _latest_json(Session)
    assert plan.min_manhattan == 3
    data = json.loads(plan.result_json)
    assert data["min_manhattan"] == 3
    assert data["hall"]["min_manhattan"] == 3

    r = c.get("/api/seating/latest?hall_id=1")
    assert r.json()["plan_min_manhattan"] == 3
    r = c.get("/api/seating/stats?hall_id=1")
    assert r.status_code == 200


def test_patch_unknown_hall_404(client):
    c, _ = client
    assert c.patch("/api/halls/999", json={"min_manhattan": 3}).status_code == 404
