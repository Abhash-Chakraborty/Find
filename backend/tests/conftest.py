"""Shared fixtures for backend API tests.

Uses in-memory SQLite with StaticPool and patches external services
(MinIO, Redis/RQ) so tests run without any infrastructure.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import JSON, Text, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Patch PostgreSQL-only column types before any model is imported.
# Stopped explicitly in the _stop_patches fixture below.
# ---------------------------------------------------------------------------
_patches = [
    patch("pgvector.sqlalchemy.Vector", lambda dim: Text()),
    patch("sqlalchemy.dialects.postgresql.ARRAY", lambda item_type: JSON()),
]
for p in _patches:
    p.start()

from fastapi.testclient import TestClient  # noqa: E402
from find_api.core.database import Base, get_db  # noqa: E402
from find_api.core.dependencies import (  # noqa: E402
    get_admin_user,
    get_required_user,
)
from find_api.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# In-memory SQLite engine with StaticPool.
# StaticPool reuses one connection so the in-memory DB is visible across
# the test thread and the ASGI app thread (TestClient runs a second thread).
# ---------------------------------------------------------------------------
_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_engine)
Base.metadata.create_all(bind=_engine)


@asynccontextmanager
async def _noop_lifespan(_app):
    """Skip real init_db / init_storage during tests."""
    yield


@pytest.fixture(scope="session", autouse=True)
def _stop_patches():
    """Stop module-level patches after the test session ends."""
    yield
    for p in _patches:
        p.stop()


@pytest.fixture()
def db():
    """Provide a clean database for each test."""
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    session = _TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """TestClient with mocked storage and queue dependencies."""

    def _override_db():
        """Create a fresh session per request (thread-safe)."""
        session = _TestSession()
        try:
            yield session
        finally:
            session.close()

    original_lifespan = app.router.lifespan_context
    app.dependency_overrides[get_db] = _override_db
    # Default tests run in local (single-user) mode: no admin exists, so the
    # auth dependencies are permissive. Overriding them here keeps that
    # behavior even when a test injects a mock/partial DB (where the real
    # is_shared_mode() query would misfire). test_auth.py opts back into the
    # real dependencies via its own fixture.
    app.dependency_overrides[get_required_user] = lambda: None
    app.dependency_overrides[get_admin_user] = lambda: None
    app.router.lifespan_context = _noop_lifespan

    fake_job = MagicMock(id="test-job-123")
    fake_queue = MagicMock()
    fake_queue.enqueue.return_value = fake_job

    try:
        with (
            patch(
                "find_api.routers.upload.upload_file", return_value="images/ab/abc.jpg"
            ),
            patch(
                "find_api.routers.upload.upload_thumbnail",
                return_value={
                    "thumbnail_key": "thumbnails/ab/abc.webp",
                    "thumbnail_content_type": "image/webp",
                    "thumbnail_size": 128,
                    "thumbnail_width": 1,
                    "thumbnail_height": 1,
                },
            ),
            patch("find_api.routers.upload.get_task_queue", return_value=fake_queue),
            patch(
                "find_api.routers.gallery.get_file_url",
                return_value="http://fake/img.jpg",
            ),
            patch("find_api.routers.gallery.delete_file"),
            patch(
                "find_api.routers.search.get_file_url",
                return_value="http://fake/img.jpg",
            ),
        ):
            with TestClient(app) as c:
                yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.router.lifespan_context = original_lifespan
