from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db import session as db_session
from app.engines.export_engine import service as export_service
from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def isolate_app_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    original_uploads_dir = settings.uploads_dir
    original_database_url = settings.database_url
    original_test_database_url = settings.test_database_url
    original_storage_backend = settings.storage_backend
    original_ai_enabled = settings.ai_enabled
    original_ai_mode_b2 = settings.ai_mode_b2
    original_ai_mode_b3 = settings.ai_mode_b3
    original_llm_api_key = settings.llm_api_key
    original_llm_api_url = settings.llm_api_url
    original_rate_limit_login = settings.rate_limit_login
    original_rate_limit_register = settings.rate_limit_register
    original_rate_limit_upload = settings.rate_limit_upload
    original_rate_limit_task_trigger = settings.rate_limit_task_trigger
    original_rate_limit_export = settings.rate_limit_export
    original_engine = db_session.engine
    original_factory = db_session.AsyncSessionFactory
    test_uploads_root = tmp_path / "uploads"
    test_database_url = settings.test_database_url or settings.database_url

    monkeypatch.setattr(settings, "uploads_dir", str(test_uploads_root))
    monkeypatch.setattr(settings, "database_url", test_database_url)
    monkeypatch.setattr(settings, "test_database_url", test_database_url)
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "ai_enabled", False)
    monkeypatch.setattr(settings, "ai_mode_b2", "rule")
    monkeypatch.setattr(settings, "ai_mode_b3", "rule")
    monkeypatch.setattr(settings, "llm_api_key", None)
    monkeypatch.setattr(settings, "llm_api_url", None)
    monkeypatch.setattr(settings, "rate_limit_login", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_register", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_upload", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_task_trigger", "1000/minute")
    monkeypatch.setattr(settings, "rate_limit_export", "1000/minute")
    monkeypatch.setattr(export_service, "EXPORTS_DIR", test_uploads_root / "_exports")

    admin_database_url = test_database_url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_database_url, future=True, isolation_level="AUTOCOMMIT")
    with admin_engine.begin() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = 'pixpress1_test'" )).scalar()
        if not exists:
            connection.execute(text('CREATE DATABASE "pixpress1_test"'))
    admin_engine.dispose()

    async_engine = create_async_engine(test_database_url, future=True, echo=False)
    db_session.engine = async_engine
    db_session.AsyncSessionFactory = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

    sync_engine = create_engine(test_database_url, future=True)
    with sync_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_database_url)
    command.upgrade(alembic_cfg, "head")

    yield

    with sync_engine.begin() as connection:
        for table in reversed(getattr(__import__("app.db.base", fromlist=["Base"]), "Base").metadata.sorted_tables):
            connection.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))

    async def _cleanup_redis() -> None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis.flushdb()
        finally:
            await redis.connection_pool.disconnect()

    asyncio.run(_cleanup_redis())

    sync_engine.dispose()
    asyncio.run(async_engine.dispose())
    db_session.engine = original_engine
    db_session.AsyncSessionFactory = original_factory
    settings.uploads_dir = original_uploads_dir
    settings.database_url = original_database_url
    settings.test_database_url = original_test_database_url
    settings.storage_backend = original_storage_backend
    settings.ai_enabled = original_ai_enabled
    settings.ai_mode_b2 = original_ai_mode_b2
    settings.ai_mode_b3 = original_ai_mode_b3
    settings.llm_api_key = original_llm_api_key
    settings.llm_api_url = original_llm_api_url
    settings.rate_limit_login = original_rate_limit_login
    settings.rate_limit_register = original_rate_limit_register
    settings.rate_limit_upload = original_rate_limit_upload
    settings.rate_limit_task_trigger = original_rate_limit_task_trigger
    settings.rate_limit_export = original_rate_limit_export


@pytest.fixture()
def client() -> TestClient:
    return TestClient(fastapi_app)
