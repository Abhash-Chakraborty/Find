"""Tests for the SQLite-backed job queue.

Covers enqueue, dequeue, completion, failure, restart persistence,
clustering coalescing, and the SQLite worker execution path.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from typing import Generator

import pytest
from sqlite3 import connect

from find_api.core.queue_sqlite import (
    JOB_STATUS_FAILED,
    JOB_STATUS_FINISHED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_STARTED,
    SQLiteQueue,
    clear_clustering_job_state,
    complete_job,
    ensure_queue_tables,
    enqueue_clustering_job_sqlite,
    fail_job,
    get_job_status,
    get_task_queue_sqlite,
    set_job_error,
    set_job_stage,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path() -> Generator[str, None, None]:
    """Provide a temporary SQLite database path for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


@pytest.fixture()
def conn(db_path: str) -> Generator:
    """Provide a clean SQLite connection with tables for each test."""
    # Patch the db path for the duration of the test
    import find_api.core.queue_sqlite as qs

    original_db_path = qs.settings.SQLITE_QUEUE_PATH
    qs.settings.SQLITE_QUEUE_PATH = db_path

    c = connect(db_path, check_same_thread=False)
    c.row_factory = __import__("sqlite3").Row
    ensure_queue_tables(c)
    try:
        yield c
    finally:
        c.close()
        qs.settings.SQLITE_QUEUE_PATH = original_db_path


@pytest.fixture()
def queue(conn) -> SQLiteQueue:
    """Provide a SQLiteQueue using the test connection."""
    return SQLiteQueue("default", connection=conn)


# ── Test helpers (job functions) ──────────────────────────────────────────────


def _dummy_success(media_id: int, tag: str = "") -> dict:
    """A dummy job function that succeeds."""
    return {"media_id": media_id, "status": "success", "tag": tag}


def _dummy_fail(media_id: int) -> dict:
    """A dummy job function that raises an error."""
    raise ValueError(f"Simulated failure for media {media_id}")


def _dummy_slow(media_id: int, sleep_seconds: float = 0.5) -> dict:
    """A dummy job function that sleeps."""
    import time

    time.sleep(sleep_seconds)
    return {"media_id": media_id, "status": "slow_success"}


# ── Table and Schema ──────────────────────────────────────────────────────────


class TestSchema:
    def test_tables_created_on_first_use(self, conn):
        """The job_queue table is created when ensure_queue_tables is called."""
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "job_queue" in table_names

    def test_schema_has_required_columns(self, conn):
        """The job_queue table has all required columns."""
        columns = {
            r["name"]: r["type"]
            for r in conn.execute("PRAGMA table_info(job_queue)").fetchall()
        }
        assert "id" in columns
        assert "queue_name" in columns
        assert "func_name" in columns
        assert "args" in columns
        assert "kwargs" in columns
        assert "status" in columns
        assert "meta" in columns
        assert "error" in columns
        assert "result" in columns
        assert "created_at" in columns
        assert "started_at" in columns
        assert "completed_at" in columns

    def test_index_on_status(self, conn):
        """Indexes exist on status and queue_name columns."""
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "ix_job_queue_status" in indexes
        assert "ix_job_queue_queue_status" in indexes


# ── Enqueue ───────────────────────────────────────────────────────────────────


class TestEnqueue:
    def test_enqueue_returns_job_with_id(self, queue, conn):
        """Enqueuing returns a SQLiteJob with a valid id."""
        job = queue.enqueue(_dummy_success, 1)
        assert job.id is not None
        assert isinstance(job.id, str)
        assert len(job.id) > 0

    def test_enqueue_stores_in_db(self, queue, conn):
        """The job row is persisted after enqueue."""
        job = queue.enqueue(_dummy_success, 42, tag="test")
        row = conn.execute("SELECT * FROM job_queue WHERE id = ?", (job.id,)).fetchone()
        assert row is not None
        assert row["status"] == JOB_STATUS_QUEUED
        assert "_dummy_success" in row["func_name"]
        assert json.loads(row["args"]) == [42]
        assert json.loads(row["kwargs"]) == {"tag": "test"}

    def test_enqueue_with_string_func_name(self, queue, conn):
        """Enqueue accepts a dotted string function name."""
        job = queue.enqueue("find_api.core.queue_sqlite:get_job_status", 1)
        assert job.func_name == "find_api.core.queue_sqlite:get_job_status"

    def test_enqueue_with_job_id(self, queue, conn):
        """Enqueue accepts a custom job_id."""
        job = queue.enqueue(_dummy_success, 1, job_id="my-custom-id")
        assert job.id == "my-custom-id"

    def test_enqueue_multiple_jobs(self, queue, conn):
        """Enqueue multiple jobs and verify they are all stored."""
        for i in range(5):
            queue.enqueue(_dummy_success, i)
        assert queue.count() == 5


# ── Dequeue ───────────────────────────────────────────────────────────────────


class TestDequeue:
    def test_dequeue_returns_oldest_queued_job(self, queue, conn):
        """Dequeue returns the oldest queued job."""
        j1 = queue.enqueue(_dummy_success, 1)
        queue.enqueue(_dummy_success, 2)
        dequeued = queue.dequeue()
        assert dequeued is not None
        assert dequeued.id == j1.id

    def test_dequeue_changes_status_to_started(self, queue, conn):
        """Dequeue atomically moves the job to 'started'."""
        queue.enqueue(_dummy_success, 1)
        dequeued = queue.dequeue()
        assert dequeued.get_status() == JOB_STATUS_STARTED

    def test_dequeue_not_returned_twice(self, queue, conn):
        """A dequeued job is not returned by dequeue again."""
        queue.enqueue(_dummy_success, 1)
        queue.dequeue()
        assert queue.dequeue() is None

    def test_dequeue_empty_queue(self, queue, conn):
        """Dequeue on an empty queue returns None."""
        assert queue.dequeue() is None

    def test_dequeue_preserves_args_and_kwargs(self, queue, conn):
        """Dequeued job preserves enqueued args and kwargs."""
        queue.enqueue(_dummy_success, 42, tag="hello")
        dequeued = queue.dequeue()
        assert dequeued.args == (42,)
        assert dequeued.kwargs == {"tag": "hello"}

    def test_dequeue_respects_queue_name(self, conn):
        """Dequeue only returns jobs from its own queue."""
        q1 = SQLiteQueue("high", connection=conn)
        q2 = SQLiteQueue("low", connection=conn)
        q1.enqueue(_dummy_success, 1)
        q2.enqueue(_dummy_success, 2)
        d1 = q1.dequeue()
        d2 = q2.dequeue()
        assert d1 is not None
        assert d2 is not None


# ── Completion and Failure ────────────────────────────────────────────────────


class TestCompletionAndFailure:
    def test_complete_job(self, queue, conn):
        """complete_job marks a job as finished with a result."""
        job = queue.enqueue(_dummy_success, 1)
        complete_job(job.id, {"result": "ok"})
        row = conn.execute("SELECT * FROM job_queue WHERE id = ?", (job.id,)).fetchone()
        assert row["status"] == JOB_STATUS_FINISHED
        assert row["completed_at"] is not None
        assert json.loads(row["result"]) == {"result": "ok"}

    def test_completed_job_get_result(self, queue, conn):
        """A completed job's result is accessible via get_result()."""
        job = queue.enqueue(_dummy_success, 1)
        complete_job(job.id, "success")
        fetched = queue.fetch_job(job.id)
        assert fetched.get_result() == "success"

    def test_fail_job(self, queue, conn):
        """fail_job marks a job as failed with an error message."""
        job = queue.enqueue(_dummy_success, 1)
        fail_job(job.id, "Something went wrong")
        row = conn.execute("SELECT * FROM job_queue WHERE id = ?", (job.id,)).fetchone()
        assert row["status"] == JOB_STATUS_FAILED
        assert row["completed_at"] is not None
        assert "Something went wrong" in row["error"]

    def test_failed_job_is_failed(self, queue, conn):
        """Failed job helper properties behave correctly."""
        job = queue.enqueue(_dummy_success, 1)
        fail_job(job.id, "error")
        fetched = queue.fetch_job(job.id)
        assert fetched.is_failed
        assert not fetched.is_finished
        assert fetched.error == "error"


# ── Job metadata ──────────────────────────────────────────────────────────────


class TestJobMetadata:
    def test_stage_is_persisted(self, queue, conn):
        """set_job_stage persists to the SQLite row."""
        job = queue.enqueue(_dummy_success, 1)
        set_job_stage(job, "processing")
        fetched = queue.fetch_job(job.id)
        assert fetched.meta["stage"] == "processing"

    def test_error_is_persisted(self, queue, conn):
        """set_job_error persists to the SQLite row."""
        job = queue.enqueue(_dummy_success, 1)
        set_job_error(job, "user-friendly error")
        fetched = queue.fetch_job(job.id)
        assert fetched.meta["error"] == "user-friendly error"

    def test_save_meta(self, queue, conn):
        """save_meta persists arbitrary metadata."""
        job = queue.enqueue(_dummy_success, 1)
        job.meta["custom_field"] = "custom_value"
        job.save_meta()
        fetched = queue.fetch_job(job.id)
        assert fetched.meta["custom_field"] == "custom_value"


# ── Fetch and Query ───────────────────────────────────────────────────────────


class TestFetchAndQuery:
    def test_fetch_job_returns_job(self, queue, conn):
        """fetch_job returns the correct job."""
        job = queue.enqueue(_dummy_success, 1)
        fetched = queue.fetch_job(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    def test_fetch_nonexistent_job(self, queue, conn):
        """fetch_job returns None for missing job."""
        assert queue.fetch_job("nonexistent") is None

    def test_get_job_ids(self, queue, conn):
        """get_job_ids returns ids filtered by status."""
        j1 = queue.enqueue(_dummy_success, 1)
        queue.enqueue(_dummy_success, 2)
        queue.enqueue(_dummy_success, 3)
        queue.dequeue()  # move j1 to started
        queued_ids = queue.get_job_ids(status=JOB_STATUS_QUEUED)
        started_ids = queue.get_job_ids(status=JOB_STATUS_STARTED)
        assert len(queued_ids) == 2
        assert len(started_ids) == 1
        assert started_ids == [j1.id]

    def test_count(self, queue, conn):
        """count returns the number of jobs matching status."""
        queue.enqueue(_dummy_success, 1)
        queue.enqueue(_dummy_success, 2)
        assert queue.count() == 2
        assert queue.count(status=JOB_STATUS_QUEUED) == 2

    def test_get_job_status(self, queue, conn):
        """get_job_status helper returns the status string."""
        job = queue.enqueue(_dummy_success, 1)
        assert get_job_status(job.id) == JOB_STATUS_QUEUED
        queue.dequeue()
        assert get_job_status(job.id) == JOB_STATUS_STARTED


# ── Queue Lifecycle ───────────────────────────────────────────────────────────


class TestQueueLifecycle:
    def test_empty_queue(self, queue, conn):
        """empty() removes all jobs from the queue."""
        queue.enqueue(_dummy_success, 1)
        queue.enqueue(_dummy_success, 2)
        queue.empty()
        assert queue.count() == 0

    def test_cleanup_expired(self, queue, conn):
        """cleanup_expired removes finished/failed jobs past their ttl."""
        job1 = queue.enqueue(_dummy_success, 1, result_ttl=0)
        job2 = queue.enqueue(_dummy_success, 2, result_ttl=0)
        complete_job(job1.id, "done")
        fail_job(job2.id, "error")
        # Ensure some time passes so ttl is expired
        time.sleep(0.01)
        removed = queue.cleanup_expired()
        assert removed == 2
        assert queue.count() == 0


# ── Persistence (Restart Survival) ────────────────────────────────────────────


class TestPersistence:
    def test_jobs_survive_connection_close(self, db_path, queue, conn):
        """Jobs committed to the database survive connection close."""
        job = queue.enqueue(_dummy_success, 42)
        conn.close()

        # Re-open with a new connection
        new_conn = connect(db_path, check_same_thread=False)
        new_conn.row_factory = __import__("sqlite3").Row
        new_queue = SQLiteQueue("default", connection=new_conn)
        try:
            fetched = new_queue.fetch_job(job.id)
            assert fetched is not None
            assert fetched.get_status() == JOB_STATUS_QUEUED
        finally:
            new_conn.close()

    def test_completed_jobs_survive_restart(self, db_path, queue, conn):
        """Completed job state persists across connections."""
        job = queue.enqueue(_dummy_success, 1)
        complete_job(job.id, {"done": True})
        conn.close()

        new_conn = connect(db_path, check_same_thread=False)
        new_conn.row_factory = __import__("sqlite3").Row
        try:
            fetched = SQLiteQueue("default", connection=new_conn).fetch_job(job.id)
            assert fetched.is_finished
            assert fetched.get_result() == {"done": True}
        finally:
            new_conn.close()

    def test_failed_jobs_survive_restart(self, db_path, queue, conn):
        """Failed job state persists across connections."""
        job = queue.enqueue(_dummy_success, 1)
        fail_job(job.id, "persistent error")
        conn.close()

        new_conn = connect(db_path, check_same_thread=False)
        new_conn.row_factory = __import__("sqlite3").Row
        try:
            fetched = SQLiteQueue("default", connection=new_conn).fetch_job(job.id)
            assert fetched.is_failed
            assert fetched.error == "persistent error"
        finally:
            new_conn.close()


# ── Clustering Coalescing ─────────────────────────────────────────────────────


class TestClusteringCoalescing:
    def test_first_enqueue_returns_queued(self, db_path):
        """First call to enqueue_clustering_job_sqlite queues the job."""
        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        result = enqueue_clustering_job_sqlite(reason="test")
        assert result["enqueued"] is True
        assert result["status"] == "queued"
        assert result["job_id"] is not None

    def test_second_enqueue_returns_already_queued(self, db_path):
        """Second call returns the existing job as already queued."""
        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        first = enqueue_clustering_job_sqlite(reason="first")
        second = enqueue_clustering_job_sqlite(reason="second")
        assert second["enqueued"] is False
        assert second["job_id"] == first["job_id"]

    def test_clear_clustering_state(self, db_path):
        """clear_clustering_job_state removes lock keys."""
        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        enqueue_clustering_job_sqlite(reason="test")
        clear_clustering_job_state()
        after = enqueue_clustering_job_sqlite(reason="after-clear")
        assert after["enqueued"] is True


# ── SQLiteJob Properties ──────────────────────────────────────────────────────


class TestSQLiteJobProperties:
    def test_job_default_properties(self, queue, conn):
        """Default job properties are sensible."""
        job = queue.enqueue(_dummy_success, 1)
        assert job.is_queued
        assert not job.is_started
        assert not job.is_finished
        assert not job.is_failed

    def test_job_after_dequeue_properties(self, queue, conn):
        """After dequeue, the job shows started status."""
        queue.enqueue(_dummy_success, 1)
        dequeued = queue.dequeue()
        assert dequeued.is_started

    def test_job_representation(self, queue, conn):
        """__repr__ returns a descriptive string."""
        job = queue.enqueue(_dummy_success, 1)
        assert "SQLiteJob" in repr(job)
        assert job.id in repr(job)


# ── Thread-local current job ──────────────────────────────────────────────────


class TestCurrentJob:
    def test_no_current_job_by_default(self):
        """get_current_job returns None when no job is active."""
        from find_api.core.queue_sqlite import (
            _clear_current_job,
            get_current_job as _current_job,
        )

        _clear_current_job()
        assert _current_job() is None

    def test_set_and_clear_current_job(self, queue, conn):
        """Set and clear the current job works correctly."""
        from find_api.core.queue_sqlite import (
            _clear_current_job,
            _set_current_job,
            get_current_job as _current_job,
        )

        job = queue.enqueue(_dummy_success, 1)
        _set_current_job(job)
        assert _current_job() is not None
        assert _current_job().id == job.id
        _clear_current_job()
        assert _current_job() is None


# ── Worker Execution ──────────────────────────────────────────────────────────


class TestWorkerExecution:
    def test_worker_runs_successful_job(self, db_path):
        """Worker executes a successful job and marks it finished."""
        from find_api.workers.sqlite_worker import execute_job

        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        queue = get_task_queue_sqlite()
        job = queue.enqueue(_dummy_success, 1, tag="worker-test")

        execute_job(job)

        fetched = queue.fetch_job(job.id)
        assert fetched.is_finished
        result = fetched.get_result()
        assert result["media_id"] == 1

    def test_worker_runs_failed_job(self, db_path):
        """Worker executes a job that fails and marks it failed."""
        from find_api.workers.sqlite_worker import execute_job

        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        queue = get_task_queue_sqlite()
        job = queue.enqueue(_dummy_fail, 99)

        execute_job(job)

        fetched = queue.fetch_job(job.id)
        assert fetched.is_failed
        assert fetched.error is not None

    def test_worker_run_once_returns_true_for_processed(self, db_path):
        """run_worker_once returns True when it processes a job."""
        from find_api.workers.sqlite_worker import run_worker_once

        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        queue = get_task_queue_sqlite()
        queue.enqueue(_dummy_success, 1)
        processed = run_worker_once(queue)
        assert processed is True

    def test_worker_run_once_returns_false_for_empty(self, db_path):
        """run_worker_once returns False for empty queue."""
        from find_api.workers.sqlite_worker import run_worker_once

        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        queue = get_task_queue_sqlite()
        processed = run_worker_once(queue)
        assert processed is False

    def test_worker_blocking_processes_max_jobs(self, db_path):
        """run_worker_blocking processes up to max_jobs jobs."""
        from find_api.workers.sqlite_worker import run_worker_blocking

        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        queue = get_task_queue_sqlite()
        queue.enqueue(_dummy_success, 1)
        queue.enqueue(_dummy_success, 2)
        queue.enqueue(_dummy_success, 3)

        run_worker_blocking(max_jobs=2)

        assert queue.count(status=JOB_STATUS_FINISHED) == 2
        assert queue.count(status=JOB_STATUS_QUEUED) == 1


# ── Status endpoint integration ───────────────────────────────────────────────


class TestStatusEndpoint:
    def test_get_job_status_returns_info(self, db_path, queue, conn):
        """get_job_status returns correct status for queued job."""
        import find_api.core.queue_sqlite as qs

        qs.settings.SQLITE_QUEUE_PATH = db_path

        job = queue.enqueue(_dummy_success, 1)
        status = get_job_status(job.id)
        assert status == JOB_STATUS_QUEUED

    def test_get_status_nonexistent(self):
        """get_job_status returns None for missing job."""
        status = get_job_status("nonexistent-id")
        assert status is None


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_enqueue_no_args(self, queue, conn):
        """Enqueue a job with no additional args."""
        job = queue.enqueue(_dummy_success)
        assert job is not None
        assert job.args == ()

    def test_enqueue_kwargs_only(self, queue, conn):
        """Enqueue a job with only kwargs."""
        job = queue.enqueue(_dummy_success, media_id=1, tag="test")
        assert job.kwargs == {"media_id": 1, "tag": "test"}

    def test_multiple_queues_independent(self, conn):
        """Multiple queue instances don't interfere."""
        q1 = SQLiteQueue("high", connection=conn)
        q2 = SQLiteQueue("low", connection=conn)
        j1 = q1.enqueue(_dummy_success, 1)
        j2 = q2.enqueue(_dummy_success, 2)
        # fetch_job reads by id regardless of queue
        assert q1.fetch_job(j1.id) is not None
        assert q1.fetch_job(j2.id) is not None
        # dequeue only returns jobs from its own queue
        assert q1.dequeue().id == j1.id
        assert q2.dequeue().id == j2.id
