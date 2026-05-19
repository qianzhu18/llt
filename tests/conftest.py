from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.main as main_mod
import app.routers.requests as requests_mod
import app.services as services_mod
from app.db import Base, get_db
from app.settings import settings


@pytest.fixture()
def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    uploads_dir = tmp_path / "uploads"
    library_dir = tmp_path / "library"
    uploads_dir.mkdir()
    library_dir.mkdir()

    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(services_mod, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(services_mod, "LIBRARY_DIR", library_dir)
    monkeypatch.setattr(requests_mod, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(main_mod._scheduler, "start", lambda: None)
    monkeypatch.setattr(main_mod._scheduler, "shutdown", lambda wait=False: None)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_mod.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main_mod.app) as client:
        client.get("/")
        yield {
            "client": client,
            "SessionLocal": SessionLocal,
            "uploads_dir": uploads_dir,
            "library_dir": library_dir,
        }

    main_mod.app.dependency_overrides.clear()
    engine.dispose()
