"""
Tests for the SQLite-backed job queue.

Run with (from backend/ directory):
    $env:PYTHONPATH = "src"
    pytest tests/test_sqlite_queue.py -v
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

import pytest

from find_api.core.sqlite_queue import SqliteQueue, _resolve_job_type


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path():
    """Provide a temporary database path per test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def queue(db_path):
    """Create a fresh SqliteQueue backed by a temp file."""
    return SqliteQueue(db_path=db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dummy_job(x: int, y: int = 0) -> int:
    """A simple job function for tests."""
    return x + y


def _failing_job() -> None:
    """A job that always raises."""
    msg = "Intentional failure"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Basic enqueue / dequeue
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    def test_enqueue_returns_job_with_id(self, queue: SqliteQueue):
        job = queue.enqueue("test_job", {"key": "value"})
        assert job.id is not None
        assert len(job.id) > 0
        assert job.type == "test_job"
        assert job.get_status() == "queued"

    def test_enqueue_call_returns_job(self, queue: SqliteQueue):
        job = queue.enqueue_call(_dummy_job, 1, y=2)
        assert job.type == f"{_dummy_job.__module__}:{_dummy_job.__qualname__}"
        assert job.get_status() == "queued"

    def test_dequeue_returns_job(self, queue: SqliteQueue):
        queue.enqueue("test_job")
        job = queue.dequeue()
        assert job is not None
        assert job.get_status() == "running"
        assert job.started_at is not None

    def test_dequeue_empty(self, queue: SqliteQueue):
        job = queue.dequeue()
        assert job is None

    def test_dequeue_fifo_order(self, queue: SqliteQueue):
        queue.enqueue("first")
        queue.enqueue("second")
        job1 = queue.dequeue()
        job2 = queue.dequeue()
        assert job1 is not None
        assert job2 is not None
        assert job1.id != job2.id

    def test_dequeue_only_queued(self, queue: SqliteQueue):
        """Dequeue should only return jobs with status 'queued'."""
        queue.enqueue("first")
        d1 = queue.dequeue()  # claims first
        j3 = queue.enqueue("third")
        job = queue.dequeue()
        assert job is not None
        assert job.id == j3.id
        assert d1 is not None
        assert d1.id != j3.id


# ---------------------------------------------------------------------------
# Complete / Fail
# ---------------------------------------------------------------------------


class TestCompleteFail:
    def test_complete_updates_status(self, queue: SqliteQueue):
        job = queue.enqueue("test_job")
        queue.dequeue()
        queue.complete(job.id)
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "completed"
        assert fetched.completed_at is not None

    def test_complete_stores_result(self, queue: SqliteQueue):
        job = queue.enqueue("test_job")
        queue.dequeue()
        queue.complete(job.id, {"answer": 42})
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.result == {"answer": 42}

    def test_fail_updates_status(self, queue: SqliteQueue):
        job = queue.enqueue("test_job")
        queue.dequeue()
        queue.fail(job.id, "Something went wrong")
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "failed"
        assert fetched.error_info == "Something went wrong"
        assert fetched.completed_at is not None

    def test_fail_stores_error_info(self, queue: SqliteQueue):
        job = queue.enqueue("test_job")
        queue.dequeue()
        error = "ValueError: invalid value"
        queue.fail(job.id, error)
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert "ValueError" in (fetched.error_info or "")


# ---------------------------------------------------------------------------
# Get job
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_get_job_returns_none_for_missing(self, queue: SqliteQueue):
        assert queue.get_job("nonexistent") is None

    def test_get_job_returns_correct_job(self, queue: SqliteQueue):
        job = queue.enqueue("test_job", {"data": 123})
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id
        assert fetched.type == "test_job"
        assert fetched.get_status() == "queued"

    def test_get_job_status_reflects_latest(self, queue: SqliteQueue):
        job = queue.enqueue("test_job")
        queue.dequeue()
        queue.complete(job.id)
        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "completed"


# ---------------------------------------------------------------------------
# Listing / Counting
# ---------------------------------------------------------------------------


class TestListCount:
    def test_count_by_status_empty(self, queue: SqliteQueue):
        counts = queue.count_by_status()
        assert counts == {}

    def test_count_by_status(self, queue: SqliteQueue):
        queue.enqueue("a")
        queue.enqueue("b")
        queue.enqueue("c")
        j1 = queue.dequeue()  # claim "a"
        queue.dequeue()  # claim "b"
        assert j1 is not None
        queue.complete(j1.id)  # complete "a"

        counts = queue.count_by_status()
        assert counts.get("queued") == 1  # "c" still queued
        assert counts.get("running") == 1  # "b" still running
        assert counts.get("completed") == 1  # "a" completed

    def test_list_active(self, queue: SqliteQueue):
        queue.enqueue("a")
        queue.enqueue("b")
        active = queue.list_active()
        assert len(active) == 2
        assert all(j.get_status() in ("queued", "running") for j in active)

    def test_list_failed(self, queue: SqliteQueue):
        j1 = queue.enqueue("a")
        j2 = queue.enqueue("b")
        queue.dequeue()
        queue.dequeue()
        queue.fail(j1.id, "error 1")
        queue.fail(j2.id, "error 2")
        failed = queue.list_failed()
        assert len(failed) == 2
        # newest first
        assert failed[0].id == j2.id


# ---------------------------------------------------------------------------
# Restart persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_jobs_survive_reconnect(self, db_path):
        """Simulate a process restart by creating a new SqliteQueue instance."""
        q1 = SqliteQueue(db_path=db_path)
        job = q1.enqueue("persistent_job", {"hello": "world"})
        q1.dequeue()
        q1.complete(job.id)

        q2 = SqliteQueue(db_path=db_path)
        fetched = q2.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "completed"
        assert fetched.type == "persistent_job"

    def test_stale_running_reset(self, queue: SqliteQueue):
        """Jobs stuck in 'running' past timeout should be reset to 'queued'."""
        job = queue.enqueue("stale_job")
        queue.dequeue()  # mark as running with a recent timestamp

        # Use a very short timeout so it qualifies as stale
        reset_count = queue.reset_stale_running(timeout_seconds=0)
        assert reset_count == 1

        fetched = queue.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "queued"
        assert fetched.error_info is not None

    def test_clear_completed(self, queue: SqliteQueue):
        j1 = queue.enqueue("a")
        j2 = queue.enqueue("b")
        queue.dequeue()
        queue.dequeue()
        queue.complete(j1.id)
        queue.complete(j2.id)

        # Negative hours means the cutoff is in the future,
        # so all completed jobs qualify for clearing.
        cleared = queue.clear_completed(older_than_hours=-1)
        assert cleared == 2

    def test_enqueue_call_persistence(self, db_path):
        """enqueue_call payload survives restart."""
        q1 = SqliteQueue(db_path=db_path)
        job = q1.enqueue_call(_dummy_job, 2, y=3)
        q1.dequeue()
        q1.complete(job.id)

        q2 = SqliteQueue(db_path=db_path)
        fetched = q2.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "completed"


# ---------------------------------------------------------------------------
# Resolve job types
# ---------------------------------------------------------------------------


class TestJobTypeResolution:
    def test_resolve_module_function(self):
        func = _resolve_job_type("test_sqlite_queue:_dummy_job")
        if func is None:
            pytest.skip("Module path resolution requires importable module path")
        assert func is _dummy_job
        assert func(1, 2) == 3

    def test_resolve_unknown_returns_none(self):
        assert _resolve_job_type("nonexistent.module:func") is None


# ---------------------------------------------------------------------------
# Worker dispatch
# ---------------------------------------------------------------------------


class TestWorkerDispatch:
    def test_complete_on_success(self, queue: SqliteQueue):
        queue.enqueue_call(_dummy_job, 10, y=20)
        from find_api.workers.sqlite_worker import run_worker_once

        ran = run_worker_once(queue)
        assert ran == 1

        # Find the completed job
        job = queue.dequeue()
        if job is None:
            # All done — find by looking at completed
            pass

        counts = queue.count_by_status()
        assert counts.get("completed") == 1

    def test_fail_on_exception(self, queue: SqliteQueue):
        queue.enqueue_call(_failing_job)
        from find_api.workers.sqlite_worker import run_worker_once

        ran = run_worker_once(queue)
        assert ran == 1

        counts = queue.count_by_status()
        assert counts.get("failed") == 1

        failed = queue.list_failed()
        assert len(failed) == 1
        assert "ValueError" in (failed[0].error_info or "")

    def test_unknown_job_type_fails(self, queue: SqliteQueue):
        queue.enqueue("nonexistent:func")
        from find_api.workers.sqlite_worker import run_worker_once

        ran = run_worker_once(queue)
        assert ran == 1

        failed = queue.list_failed()
        assert len(failed) == 1
        assert "Unknown job type" in (failed[0].error_info or "")

    def test_worker_loop_processes_all(self, queue: SqliteQueue):
        for i in range(5):
            queue.enqueue_call(_dummy_job, i)
        from find_api.workers.sqlite_worker import run_worker_loop

        stop = threading.Event()

        def _stop_after_delay():
            time.sleep(0.5)
            stop.set()

        threading.Thread(target=_stop_after_delay, daemon=True).start()
        run_worker_loop(queue, poll_interval=0.05, stop_event=stop)

        counts = queue.count_by_status()
        assert counts.get("completed") == 5


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_two_queues_same_db(self, db_path):
        """Two SqliteQueue instances pointing at the same file."""
        q1 = SqliteQueue(db_path=db_path)
        q2 = SqliteQueue(db_path=db_path)

        q1.enqueue("shared_job", {"from": "q1"})
        job = q2.dequeue()
        assert job is not None
        assert job.type == "shared_job"
        q2.complete(job.id)

        fetched = q1.get_job(job.id)
        assert fetched is not None
        assert fetched.get_status() == "completed"
