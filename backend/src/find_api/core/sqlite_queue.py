"""SQLite-backed durable job queue for desktop mode."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from find_api.core.config import settings

logger = logging.getLogger(__name__)

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS job_queue (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','completed','failed')),
    payload     TEXT NOT NULL DEFAULT '{}',
    error_info  TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    completed_at TEXT
)
"""

SQL_ENQUEUE = """
INSERT INTO job_queue (id, type, status, payload, created_at)
VALUES (?, ?, 'queued', ?, ?)
"""

SQL_DEQUEUE = """
UPDATE job_queue
SET status = 'running', started_at = ?
WHERE id = (
    SELECT id FROM job_queue
    WHERE status = 'queued'
    ORDER BY created_at ASC
    LIMIT 1
)
RETURNING id, type, payload, created_at
"""

SQL_COMPLETE = """
UPDATE job_queue
SET status = 'completed', completed_at = ?, error_info = NULL
WHERE id = ?
"""

SQL_FAIL = """
UPDATE job_queue
SET status = 'failed', completed_at = ?, error_info = ?
WHERE id = ?
"""

SQL_GET_JOB = """
SELECT id, type, status, payload, error_info, created_at, started_at, completed_at
FROM job_queue
WHERE id = ?
"""

SQL_LIST_ACTIVE = """
SELECT id, type, status, payload, error_info, created_at, started_at, completed_at
FROM job_queue
WHERE status IN ('queued', 'running')
ORDER BY created_at ASC
"""

SQL_LIST_FAILED = """
SELECT id, type, status, payload, error_info, created_at, started_at, completed_at
FROM job_queue
WHERE status = 'failed'
ORDER BY completed_at DESC
"""

SQL_COUNT_STATUS = """
SELECT status, COUNT(*) as cnt FROM job_queue GROUP BY status
"""

SQL_CLEAR_COMPLETED = """
DELETE FROM job_queue WHERE status = 'completed' AND completed_at < ?
"""

SQL_RESET_STALE = """
UPDATE job_queue
SET status = 'queued', started_at = NULL, error_info = ?
WHERE status = 'running' AND started_at < ?
"""

SQL_CREATE_CLUSTERING_LOCKS = """
CREATE TABLE IF NOT EXISTS clustering_locks (
    key         TEXT PRIMARY KEY,
    reason      TEXT NOT NULL,
    expires_at  TEXT NOT NULL
)
"""

SQL_ACQUIRE_CLUSTERING_LOCK = """
INSERT INTO clustering_locks (key, reason, expires_at)
VALUES (?, ?, ?)
ON CONFLICT(key) DO NOTHING
"""

SQL_RELEASE_CLUSTERING_LOCK = """
DELETE FROM clustering_locks WHERE key = ?
"""

SQL_CLEANUP_EXPIRED_LOCKS = """
DELETE FROM clustering_locks WHERE expires_at < ?
"""


class SqliteJob:
    """Proxy object for a job stored in the SQLite queue."""

    def __init__(self, row: dict[str, Any]) -> None:
        self.id: str = row["id"]
        self.type: str = row["type"]
        self._status: str = row["status"]
        self._payload: Any = json.loads(row["payload"]) if row.get("payload") else {}
        self.error_info: str | None = row.get("error_info")
        self.created_at: str | None = row.get("created_at")
        self.started_at: str | None = row.get("started_at")
        self.completed_at: str | None = row.get("completed_at")
        self.meta: dict[str, Any] = self._payload.get("meta", {})
        self.result: Any = self._payload.get("result")

    def get_status(self) -> str:
        return self._status

    @property
    def is_finished(self) -> bool:
        return self._status == "completed"

    @property
    def is_failed(self) -> bool:
        return self._status == "failed"


class SqliteQueue:
    """Durable SQLite-backed job queue.

    Each job is stored as a row in the ``job_queue`` table.  The queue
    supports concurrent enqueue / dequeue from multiple processes on the
    same host (one writer at a time via SQLite locking).
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.QUEUE_DB_PATH
        self._local = threading.local()
        self._init_db()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Get a thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_db(self) -> None:
        """Create the job_queue and clustering_locks tables if they do not exist."""
        conn = self._conn()
        conn.execute(SQL_CREATE_TABLE)
        conn.execute(SQL_CREATE_CLUSTERING_LOCKS)
        conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
    ) -> SqliteJob:
        """Enqueue a new job and return a SqliteJob proxy."""
        job_id = str(uuid.uuid4())
        now = _now_str()
        payload_str = json.dumps(payload or {})
        conn = self._conn()
        conn.execute(SQL_ENQUEUE, (job_id, job_type, payload_str, now))
        conn.commit()
        logger.debug("Enqueued job %s (%s)", job_id, job_type)
        return SqliteJob(
            {
                "id": job_id,
                "type": job_type,
                "status": "queued",
                "payload": payload_str,
                "error_info": None,
                "created_at": now,
                "started_at": None,
                "completed_at": None,
            }
        )

    def enqueue_call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> SqliteJob:
        """Enqueue a job by storing the importable function reference.

        This mirrors the RQ ``Queue.enqueue`` signature so callers can
        use the same pattern.
        """
        module = func.__module__
        qualname = func.__qualname__
        job_type = f"{module}:{qualname}"
        payload = {"args": _serialize_args(args), "kwargs": _serialize_kwargs(kwargs)}
        return self.enqueue(job_type, payload)

    def dequeue(self) -> SqliteJob | None:
        """Atomically claim the next queued job.

        Returns ``None`` when the queue is empty.
        """
        conn = self._conn()
        now = _now_str()
        try:
            cursor = conn.execute(SQL_DEQUEUE, (now,))
            row = cursor.fetchone()
            conn.commit()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        return SqliteJob(
            {
                "id": row["id"],
                "type": row["type"],
                "status": "running",
                "payload": row["payload"],
                "error_info": None,
                "created_at": row["created_at"],
                "started_at": now,
                "completed_at": None,
            }
        )

    def complete(self, job_id: str, result: Any = None) -> None:
        """Mark a job as completed, optionally storing a result."""
        sql = SQL_COMPLETE
        params: list[Any] = [_now_str(), job_id]
        if result is not None:
            existing = self.get_job(job_id)
            if existing:
                payload = dict(existing._payload)
                payload["result"] = result
                self._update_payload(job_id, payload)
        conn = self._conn()
        conn.execute(sql, params)
        conn.commit()

    def fail(self, job_id: str, error_info: str) -> None:
        """Mark a job as failed with an error message."""
        conn = self._conn()
        conn.execute(SQL_FAIL, (_now_str(), error_info, job_id))
        conn.commit()

    def get_job(self, job_id: str) -> SqliteJob | None:
        """Fetch a job by id."""
        conn = self._conn()
        cursor = conn.execute(SQL_GET_JOB, (job_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return SqliteJob(dict(row))

    def list_failed(self) -> list[SqliteJob]:
        """Return all failed jobs, newest first."""
        conn = self._conn()
        cursor = conn.execute(SQL_LIST_FAILED)
        return [SqliteJob(dict(row)) for row in cursor.fetchall()]

    def list_active(self) -> list[SqliteJob]:
        """Return all queued and running jobs."""
        conn = self._conn()
        cursor = conn.execute(SQL_LIST_ACTIVE)
        return [SqliteJob(dict(row)) for row in cursor.fetchall()]

    def count_by_status(self) -> dict[str, int]:
        """Return a dict mapping status -> count."""
        conn = self._conn()
        cursor = conn.execute(SQL_COUNT_STATUS)
        return {row["status"]: row["cnt"] for row in cursor.fetchall()}

    def clear_completed(self, older_than_hours: int = 24) -> int:
        """Remove completed jobs older than the given threshold."""
        cutoff = _now_str(-older_than_hours * 3600)
        conn = self._conn()
        cursor = conn.execute(SQL_CLEAR_COMPLETED, (cutoff,))
        conn.commit()
        return cursor.rowcount

    def reset_stale_running(self, timeout_seconds: int = 600) -> int:
        """Reset running jobs that have exceeded the timeout back to queued."""
        cutoff = _now_str(-timeout_seconds)
        conn = self._conn()
        cursor = conn.execute(
            SQL_RESET_STALE,
            (f"Reset after timeout ({timeout_seconds}s)", cutoff),
        )
        conn.commit()
        return cursor.rowcount

    def _update_payload(self, job_id: str, payload: dict[str, Any]) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE job_queue SET payload = ? WHERE id = ?",
            (json.dumps(payload), job_id),
        )
        conn.commit()

    def acquire_clustering_lock(self, key: str, reason: str, ttl_seconds: int) -> bool:
        """Atomically acquire a clustering lock.

        Returns True if this caller acquired the lock, False if another
        caller already holds it.
        """
        conn = self._conn()
        conn.execute(SQL_CLEANUP_EXPIRED_LOCKS, (_now_str(),))
        expires_at = _now_str(ttl_seconds)
        cursor = conn.execute(SQL_ACQUIRE_CLUSTERING_LOCK, (key, reason, expires_at))
        conn.commit()
        return cursor.rowcount > 0

    def release_clustering_lock(self, key: str) -> None:
        """Release a clustering lock."""
        conn = self._conn()
        conn.execute(SQL_RELEASE_CLUSTERING_LOCK, (key,))
        conn.commit()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

_JOB_TYPE_DISPATCH: dict[str, Callable[..., Any]] = {}


def register_job(job_type: str, func: Callable[..., Any]) -> None:
    """Register a callable for a given job type string."""
    _JOB_TYPE_DISPATCH[job_type] = func


def _resolve_job_type(job_type: str) -> Callable[..., Any] | None:
    """Resolve a ``module:qualname`` string to a callable.

    Falls back to the local dispatch dict for known names.
    """
    if job_type in _JOB_TYPE_DISPATCH:
        return _JOB_TYPE_DISPATCH[job_type]
    if ":" in job_type:
        module_path, qualname = job_type.split(":", 1)
        try:
            import importlib

            mod = importlib.import_module(module_path)
            return _resolve_attr(mod, qualname)
        except (ImportError, AttributeError):
            return None
    return None


def _resolve_attr(obj: Any, attr_path: str) -> Any:
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


def _serialize_args(args: tuple[Any, ...]) -> list[Any]:
    result: list[Any] = []
    for a in args:
        if isinstance(a, (str, int, float, bool, list, dict, type(None))):
            result.append(a)
        else:
            result.append(str(a))
    return result


def _serialize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in kwargs.items():
        if isinstance(v, (str, int, float, bool, list, dict, type(None))):
            result[k] = v
        else:
            result[k] = str(v)
    return result


def _now_str(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


def _parse_time(ts: str | None) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
