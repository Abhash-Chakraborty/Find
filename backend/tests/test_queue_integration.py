"""
Tests for the unified queue interface (core/queue.py).

Verifies that the abstraction layer correctly dispatches to the SQLite
backend when QUEUE_MODE=sqlite.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from unittest.mock import patch

from find_api.core.config import settings


@pytest.fixture(autouse=True)
def _reset_backend():
    """Reset the queue backend cache before each test."""
    import find_api.core.queue as qm

    qm._BACKEND = None
    yield
    qm._BACKEND = None


@pytest.fixture()
def sqlite_settings():
    """Temporarily switch to SQLite queue mode with a temp DB."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with (
        patch.object(settings, "QUEUE_MODE", "sqlite"),
        patch.object(settings, "QUEUE_DB_PATH", path),
    ):
        yield
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _sample_job(x: int) -> int:
    return x * 2


# ---------------------------------------------------------------------------
# SQLite mode integration
# ---------------------------------------------------------------------------


class TestSqliteIntegration:
    def test_enqueue_job(self, sqlite_settings):
        from find_api.core.queue import enqueue_job

        job = enqueue_job(_sample_job, 21)
        assert job.id is not None
        assert "sample_job" in job.type

    def test_get_job(self, sqlite_settings):
        from find_api.core.queue import enqueue_job, get_job

        job = enqueue_job(_sample_job, 21)
        fetched = get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id
        assert fetched.get_status() in ("queued", "running", "completed", "failed")

    def test_enqueue_clustering_job(self, sqlite_settings):
        """Clustering job coalescing should work in SQLite mode."""
        from find_api.core.queue import enqueue_clustering_job

        result = enqueue_clustering_job(reason="test")
        assert result["enqueued"] is True
        assert result["status"] == "queued"
        assert "job_id" in result

    def test_enqueue_clustering_dedup(self, sqlite_settings):
        """Second clustering request should return existing job."""
        from find_api.core.queue import enqueue_clustering_job

        r1 = enqueue_clustering_job(reason="first")
        assert r1["enqueued"] is True
        r2 = enqueue_clustering_job(reason="second")
        assert r2["enqueued"] is False
        assert r2["job_id"] == r1["job_id"]

    def test_get_task_queue(self, sqlite_settings):
        from find_api.core.queue import get_task_queue

        q = get_task_queue()
        from find_api.core.sqlite_queue import SqliteQueue

        assert isinstance(q, SqliteQueue)

    def test_redis_connection_raises(self, sqlite_settings):
        from find_api.core.queue import get_redis_connection

        with pytest.raises(RuntimeError):
            get_redis_connection()


# ---------------------------------------------------------------------------
# Redis mode unchanged
# ---------------------------------------------------------------------------


class TestRedisMode:
    def test_redis_unchanged_imports(self):
        """Redis mode imports should still work."""
        from find_api.core.queue import (
            CLUSTERING_LOCK_KEY,
        )

        assert CLUSTERING_LOCK_KEY == "find:clustering:queued"
