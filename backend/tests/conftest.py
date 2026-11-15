import os
import shutil
import tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="campusflow-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'baseline.db').as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import db
from app.seed import load
from app.services import snapshot as snapshot_service


@pytest.fixture(scope="session")
def baseline_path() -> Path:
    db.configure(f"sqlite:///{(TEST_DIR / 'baseline.db').as_posix()}")
    load.seed_database(rebuild=True)
    db.get_engine().dispose()
    return TEST_DIR / "baseline.db"


@pytest.fixture(scope="session")
def readonly_session(baseline_path: Path):
    db.configure(f"sqlite:///{baseline_path.as_posix()}")
    snapshot_service.reset_cache()
    with Session(db.get_engine()) as session:
        yield session


@pytest.fixture
def session(baseline_path: Path, tmp_path: Path):
    target = tmp_path / "test.db"
    shutil.copy(baseline_path, target)
    db.configure(f"sqlite:///{target.as_posix()}")
    snapshot_service.reset_cache()
    with Session(db.get_engine()) as active:
        yield active


@pytest.fixture
def client(session: Session):
    from app.deps import reset_rate_limits
    from app.main import app

    reset_rate_limits()
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, name: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": f"{name}@jklu.demo", "password": "Demo@1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def fresh(session: Session) -> None:
    session.rollback()
    session.expire_all()

