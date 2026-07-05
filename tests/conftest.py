from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.db.database import Base, get_db
from backend.main import app
from backend.services.reconstruction import clear_rec_logs

TEST_DB_URL = "sqlite:///./data/test_drone_mapping.db"

test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def setup_test_db():
    from backend.db import models  # noqa: F401
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_tables(request):
    if "tests/backend" not in request.node.path.as_posix():
        yield
        return

    request.getfixturevalue("setup_test_db")
    clear_rec_logs()
    yield
    clear_rec_logs()
    with TestSessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()


@pytest.fixture(scope="session")
def db_engine():
    return test_engine


@pytest.fixture
def client():
    return TestClient(app)
