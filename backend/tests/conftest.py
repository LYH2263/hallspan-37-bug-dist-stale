import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import Candidate, Hall, PaperSet


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def hall_with_candidates(db):
    """5x6 考室（对角线上限 9），12 名考生，3 种卷；初始距离 2。"""
    hall = Hall(code="H101", name="一号考室", rows=5, cols=6, min_manhattan=2)
    db.add(hall)
    db.flush()
    pids = []
    for code in ("P-A", "P-B", "P-C"):
        p = PaperSet(code=code, title=code)
        db.add(p)
        db.flush()
        pids.append(p.id)
    for i in range(12):
        db.add(Candidate(hall_id=hall.id, name=f"考生{i}", ticket_no=f"T{i}",
                         paper_id=pids[i % 3]))
    db.commit()
    return hall
