"""Durable SQLite-backed job queue for desktop mode.

Provides a Redis/RQ-compatible interface using SQLite for persistence,
allowing jobs to survive process restarts without requiring a Redis server.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable

from find_api.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_STARTED = "started"
JOB_STATUS_FINISHED = "finished"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_DEFERRED = "deferred"
JOB_STATUS_SCHEDULED = "scheduled"
JOB_STATUS_STOPPED = "stopped"
JOB_STATUS_CANCELED = "canceled"

ACTIVE_JOB_STATUSES = {
    JOB_STATUS_QUEUED,
    JOB_STATUS_STARTED,
    JOB_STATUS_DEFERRED,
    JOB_STATUS_SCHEDULED,
}
FAILED_JOB_STATUSES = {JOB_STATUS_FAILED, JOB_STATUS_STOPPED, JOB_STATUS_CANCELED}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS job_queue (
    id TEXT PRIMARY KEY,
    queue_name TEXT NOT NULL DEFAULT 'default',
    func_name TEXT NOT NULL,
    args TEXT,
    kwargs TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    meta TEXT DEFAULT '{}',
    error TEXT,
    result TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    job_timeout REAL,
    result_ttl REAL
);

CREATE INDEX IF NOT EXISTS ix_job_queue_status ON job_queue (status);
CREATE INDEX IF NOT EXISTS ix_job_queue_queue_status ON job_queue (queue_name, status);
CREATE INDEX IF NOT EXISTS ix_job_queue_created ON job_queue (created_at);
"""

CLUSTERING_LOCK_KEY = "find:clustering:queued"
CLUSTERING_JOB_ID_KEY = "find:clustering:job-id"

# ---------------------------------------------------------------------------
# Thread-local current job support (replaces rq.get_current_job)
# ---------------------------------------------------------------------------

_current_job = threading.local()


def get_current_job():
    """Return the currently executing SQLiteJob or None."""
    return getattr(_current_job, "job", None)


def _set_current_job(job):
    _current_job.job = job


def _clear_current_job():
    _current_job.job = None


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _get_db_path() -> str:
    """Return the SQLite database path for the job queue."""
    if settings.SQLITE_QUEUE_PATH:
        return settings.SQLITE_QUEUE_PATH
    return os.path.join(os.path.expanduser("~"), ".find", "queue.db")


def _get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with WAL mode for concurrency."""
    db_path = _get_db_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------


def ensure_queue_tables(conn: sqlite3.Connection | None = None) -> None:
    """Create the job queue table if it does not exist."""
    if conn is None:
        conn = _get_connection()
        should_close = True
    else:
        should_close = False
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Function resolution
# ---------------------------------------------------------------------------


def _resolve_func(func: str | Callable) -> tuple[str, Callable]:
    """Return (qualified_name, callable) from a function or dotted string.

    The qualified name uses colon syntax: ``module.path:func_name``
    which is compatible with RQ's job serialization format.
    """
    if callable(func):
        qualified = f"{func.__module__}:{func.__name__}"
        return qualified, func

    if isinstance(func, str):
        if ":" not in func:
            raise ValueError(
                f"Function spec must use 'module:name' format, got: {func}"
            )
        module_path, func_name = func.rsplit(":", 1)
        module = importlib.import_module(module_path)
        resolved = getattr(module, func_name)
        return func, resolved

    raise TypeError(f"Expected callable or string, got {type(func)}")


# ---------------------------------------------------------------------------
# Job class
# ---------------------------------------------------------------------------


class SQLiteJob:
    """A single job record mirroring the RQ Job interface."""

    def __init__(self, id: str, row: dict[str, Any] | None = None):
        self.id = id
        self._row = row or {}
        self.meta: dict[str, Any] = {}

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SQLiteJob:
        """Create a job from a database row."""
        job = cls(id=row["id"])
        data = dict(row)
        job._row = data

        raw_meta = data.get("meta")
        if raw_meta:
            try:
                job.meta = (
                    json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                )
            except (json.JSONDecodeError, TypeError):
                job.meta = {}
        else:
            job.meta = {}

        return job

    def get_status(self) -> str:
        """Return the current job status."""
        return self._row.get("status", JOB_STATUS_QUEUED)

    def get_result(self, *, override_result_ttl: int | None = None):
        """Return the stored result."""
        raw = self._row.get("result")
        if raw is None:
            return None
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return raw

    @property
    def func_name(self) -> str | None:
        return self._row.get("func_name")

    @property
    def args(self) -> tuple:
        raw = self._row.get("args")
        if not raw:
            return ()
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            return tuple(parsed) if isinstance(parsed, list) else (parsed,)
        except (json.JSONDecodeError, TypeError):
            return ()

    @property
    def kwargs(self) -> dict:
        raw = self._row.get("kwargs")
        if not raw:
            return {}
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def error(self) -> str | None:
        return self._row.get("error")

    @property
    def created_at(self) -> float | None:
        return self._row.get("created_at")

    @property
    def started_at(self) -> float | None:
        return self._row.get("started_at")

    @property
    def completed_at(self) -> float | None:
        return self._row.get("completed_at")

    @property
    def is_failed(self) -> bool:
        return self._row.get("status") == JOB_STATUS_FAILED

    @property
    def is_finished(self) -> bool:
        return self._row.get("status") == JOB_STATUS_FINISHED

    @property
    def is_queued(self) -> bool:
        return self._row.get("status") == JOB_STATUS_QUEUED

    @property
    def is_started(self) -> bool:
        return self._row.get("status") == JOB_STATUS_STARTED

    def save_meta(self) -> None:
        """Persist the current meta dict to the database."""
        conn = _get_connection()
        try:
            conn.execute(
                "UPDATE job_queue SET meta = ? WHERE id = ?",
                (json.dumps(self.meta), self.id),
            )
            conn.commit()
        finally:
            conn.close()

    def __repr__(self) -> str:
        return f"<SQLiteJob {self.id} status={self.get_status()}>"


# ---------------------------------------------------------------------------
# Queue class
# ---------------------------------------------------------------------------


class SQLiteQueue:
    """SQLite-backed job queue compatible with the RQ Queue interface."""

    def __init__(
        self, name: str = "default", connection: sqlite3.Connection | None = None
    ):
        self.name = name
        self._connection = connection

    def _get_conn(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        return _get_connection()

    def enqueue(
        self,
        func: str | Callable,
        *args: Any,
        job_timeout: int | None = None,
        result_ttl: int | None = None,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> SQLiteJob:
        """Enqueue a job and return the job instance."""
        func_name, _ = _resolve_func(func)
        job_id = job_id or str(uuid.uuid4())
        now = time.time()

        conn = self._get_conn()
        should_close = self._connection is None
        try:
            conn.execute(
                """INSERT INTO job_queue
                   (id, queue_name, func_name, args, kwargs, status, meta,
                    created_at, job_timeout, result_ttl)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    self.name,
                    func_name,
                    json.dumps(list(args)),
                    json.dumps(kwargs),
                    JOB_STATUS_QUEUED,
                    "{}",
                    now,
                    job_timeout,
                    result_ttl,
                ),
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM job_queue WHERE id = ?", (job_id,)
            ).fetchone()
            return SQLiteJob.from_row(row)
        finally:
            if should_close:
                conn.close()

    def fetch_job(self, job_id: str) -> SQLiteJob | None:
        """Fetch a job by id, returning None if not found."""
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            row = conn.execute(
                "SELECT * FROM job_queue WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            return SQLiteJob.from_row(row)
        finally:
            if should_close:
                conn.close()

    def dequeue(self) -> SQLiteJob | None:
        """Claim the oldest queued job atomically.

        Returns None when no job is available.
        """
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            while True:
                row = conn.execute(
                    """SELECT * FROM job_queue
                       WHERE queue_name = ? AND status = ?
                       ORDER BY created_at ASC
                       LIMIT 1""",
                    (self.name, JOB_STATUS_QUEUED),
                ).fetchone()

                if row is None:
                    return None

                now = time.time()
                job_id = row["id"]

                cur = conn.execute(
                    "UPDATE job_queue SET status = ?, started_at = ? WHERE id = ? AND status = ?",
                    (JOB_STATUS_STARTED, now, job_id, JOB_STATUS_QUEUED),
                )
                conn.commit()

                if cur.rowcount > 0:
                    updated = conn.execute(
                        "SELECT * FROM job_queue WHERE id = ?", (job_id,)
                    ).fetchone()
                    return SQLiteJob.from_row(updated)
        finally:
            if should_close:
                conn.close()

    def get_job_ids(self, status: str | None = None) -> list[str]:
        """Return job IDs matching the given status, or all jobs."""
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            if status:
                rows = conn.execute(
                    "SELECT id FROM job_queue WHERE queue_name = ? AND status = ? ORDER BY created_at",
                    (self.name, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM job_queue WHERE queue_name = ? ORDER BY created_at",
                    (self.name,),
                ).fetchall()
            return [r["id"] for r in rows]
        finally:
            if should_close:
                conn.close()

    def get_all_jobs(self) -> list[SQLiteJob]:
        """Return all jobs in the queue."""
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            rows = conn.execute(
                "SELECT * FROM job_queue WHERE queue_name = ? ORDER BY created_at",
                (self.name,),
            ).fetchall()
            return [SQLiteJob.from_row(r) for r in rows]
        finally:
            if should_close:
                conn.close()

    def count(self, status: str | None = None) -> int:
        """Count jobs, optionally filtered by status."""
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            if status:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM job_queue WHERE queue_name = ? AND status = ?",
                    (self.name, status),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM job_queue WHERE queue_name = ?",
                    (self.name,),
                ).fetchone()
            return row["cnt"] if row else 0
        finally:
            if should_close:
                conn.close()

    def empty(self) -> None:
        """Remove all jobs from the queue."""
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            conn.execute("DELETE FROM job_queue WHERE queue_name = ?", (self.name,))
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def cleanup_expired(self) -> int:
        """Remove finished/failed jobs past their result_ttl.

        Returns the number of removed jobs.
        """
        conn = self._get_conn()
        should_close = self._connection is None
        try:
            now = time.time()
            removed = conn.execute(
                """DELETE FROM job_queue
                   WHERE queue_name = ?
                   AND status IN (?, ?)
                   AND result_ttl IS NOT NULL
                   AND completed_at IS NOT NULL
                   AND (completed_at + result_ttl) < ?""",
                (self.name, JOB_STATUS_FINISHED, JOB_STATUS_FAILED, now),
            ).rowcount
            if removed:
                conn.commit()
            return removed
        finally:
            if should_close:
                conn.close()


# ---------------------------------------------------------------------------
# Job lifecycle helpers
# ---------------------------------------------------------------------------


def complete_job(job_id: str, result: Any = None) -> None:
    """Mark a job as finished and store its result."""
    conn = _get_connection()
    try:
        conn.execute(
            """UPDATE job_queue
               SET status = ?, completed_at = ?, result = ?
               WHERE id = ?""",
            (
                JOB_STATUS_FINISHED,
                time.time(),
                json.dumps(result) if result is not None else None,
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fail_job(job_id: str, error: str, result: Any = None) -> None:
    """Mark a job as failed and store the error."""
    conn = _get_connection()
    try:
        conn.execute(
            """UPDATE job_queue
               SET status = ?, completed_at = ?, error = ?, result = ?
               WHERE id = ?""",
            (
                JOB_STATUS_FAILED,
                time.time(),
                error,
                json.dumps(result) if result is not None else None,
                job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def set_job_stage(job: SQLiteJob, stage: str) -> None:
    """Persist the current processing stage in job metadata."""
    if job:
        job.meta["stage"] = stage
        job.save_meta()


def set_job_error(job: SQLiteJob, error: str) -> None:
    """Persist a safe user-facing processing error in job metadata."""
    if job:
        job.meta["error"] = error
        job.save_meta()


# ---------------------------------------------------------------------------
# Clustering coalescing helpers (SQLite variant)
# ---------------------------------------------------------------------------


def _cluster_lock_ttl() -> int:
    """Keep the clustering lock long enough for queued jobs to drain."""
    return max(settings.WORKER_TIMEOUT * 4, 1800)


def clear_clustering_job_state() -> None:
    """Clear SQLite-based clustering lock state."""
    conn = _get_connection()
    try:
        conn.execute(
            "DELETE FROM job_queue WHERE id IN (?, ?)",
            (CLUSTERING_LOCK_KEY, CLUSTERING_JOB_ID_KEY),
        )
        conn.commit()
    finally:
        conn.close()


def get_task_queue_sqlite(name: str = "default") -> SQLiteQueue:
    """Create a SQLiteQueue instance."""
    ensure_queue_tables()
    return SQLiteQueue(name)


def enqueue_clustering_job_sqlite(*, reason: str) -> dict[str, Any]:
    """Enqueue clustering once using SQLite-backed locking."""
    ensure_queue_tables()
    conn = _get_connection()
    try:
        ttl = _cluster_lock_ttl()
        now = time.time()
        expiry = now + ttl

        cur = conn.execute(
            """INSERT INTO job_queue (id, func_name, status, meta, created_at, job_timeout)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO NOTHING""",
            (
                CLUSTERING_LOCK_KEY,
                "__lock__",
                "locked",
                json.dumps({"reason": reason, "expires_at": expiry}),
                now,
                ttl,
            ),
        )

        if cur.rowcount == 0:
            ref_row = conn.execute(
                "SELECT * FROM job_queue WHERE id = ?", (CLUSTERING_JOB_ID_KEY,)
            ).fetchone()

            if ref_row:
                meta = json.loads(ref_row["meta"]) if ref_row["meta"] else {}
                job_id = meta.get("job_id")
                if job_id:
                    job_row = conn.execute(
                        "SELECT * FROM job_queue WHERE id = ?", (job_id,)
                    ).fetchone()
                    if job_row:
                        job_status = job_row["status"]
                        if job_status in ACTIVE_JOB_STATUSES:
                            return {
                                "job_id": job_id,
                                "message": "Clustering job already queued",
                                "enqueued": False,
                                "status": job_status,
                            }

            clear_clustering_job_state()
            return enqueue_clustering_job_sqlite(reason=reason)

        from find_api.workers.jobs import cluster_images

        queue = SQLiteQueue("default", connection=conn)
        job = queue.enqueue(
            cluster_images,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )

        conn.execute(
            """INSERT INTO job_queue (id, func_name, status, meta, created_at, job_timeout)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                CLUSTERING_JOB_ID_KEY,
                "__ref__",
                "active",
                json.dumps({"job_id": job.id, "expires_at": expiry}),
                now,
                ttl,
            ),
        )
        conn.commit()

        logger.info("Queued clustering job %s (%s)", job.id, reason)
        return {
            "job_id": job.id,
            "message": "Clustering job queued",
            "enqueued": True,
            "status": "queued",
        }

    finally:
        conn.close()


def get_job_status(job_id: str | None) -> str | None:
    """Return the status of a job by id."""
    if not job_id:
        return None
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM job_queue WHERE id = ?", (job_id,)
        ).fetchone()
        return row["status"] if row else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()
