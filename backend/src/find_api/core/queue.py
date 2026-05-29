"""Queue helpers for background jobs.

Supports both Redis/RQ (Docker/server mode) and SQLite (desktop mode).
The backend is selected via ``settings.QUEUE_BACKEND``.
"""

from __future__ import annotations

import logging
from typing import Any

from redis import Redis
from rq import Queue  # type: ignore[import-untyped]
from rq.job import Job  # type: ignore[import-untyped]

from find_api.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_NAME = "default"
CLUSTERING_LOCK_KEY = "find:clustering:queued"
CLUSTERING_JOB_ID_KEY = "find:clustering:job-id"


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def get_queue_backend() -> str:
    """Return the active queue backend name ('redis' or 'sqlite')."""
    return settings.QUEUE_BACKEND


def is_sqlite_backend() -> bool:
    """Return True when the SQLite queue backend is active."""
    return settings.QUEUE_BACKEND == "sqlite"


# ---------------------------------------------------------------------------
# Redis / RQ helpers
# ---------------------------------------------------------------------------


def get_redis_connection() -> Redis:
    """Create a Redis connection for queue operations."""
    return Redis.from_url(settings.REDIS_URL)


def get_task_queue_rq(name: str = DEFAULT_QUEUE_NAME) -> Queue:
    """Create an RQ queue instance."""
    return Queue(name, connection=get_redis_connection())


# ---------------------------------------------------------------------------
# SQLite helpers (lazy-imported to keep RQ mode dependency-free)
# ---------------------------------------------------------------------------


def _get_sqlite_queue(name: str = DEFAULT_QUEUE_NAME):
    """Lazy-import and return a SQLiteQueue instance."""
    from find_api.core.queue_sqlite import get_task_queue_sqlite

    return get_task_queue_sqlite(name)


def _enqueue_clustering_sqlite(*, reason: str) -> dict[str, Any]:
    from find_api.core.queue_sqlite import enqueue_clustering_job_sqlite

    return enqueue_clustering_job_sqlite(reason=reason)


def _clear_clustering_sqlite() -> None:
    from find_api.core.queue_sqlite import clear_clustering_job_state

    clear_clustering_job_state()


def _sqlite_job_status(job_id: str | None) -> str | None:
    if not job_id:
        return None
    from find_api.core.queue_sqlite import get_job_status

    return get_job_status(job_id)


# ---------------------------------------------------------------------------
# Unified factory functions (used by routers and workers)
# ---------------------------------------------------------------------------


def get_task_queue(name: str = DEFAULT_QUEUE_NAME):
    """Return a queue instance for the active backend.

    In Redis/RQ mode, returns an ``rq.Queue``.
    In SQLite mode, returns a ``SQLiteQueue``.
    Both expose ``.enqueue(func, *args, **kwargs)`` returning a job-like object
    with ``.id``, ``.get_status()``, and ``.meta``.
    """
    if is_sqlite_backend():
        return _get_sqlite_queue(name)
    return get_task_queue_rq(name)


def get_current_job():
    """Return the currently executing job, backend-agnostic.

    In RQ mode, calls ``rq.get_current_job()``.
    In SQLite mode, calls the SQLite thread-local current job.
    """
    if is_sqlite_backend():
        from find_api.core.queue_sqlite import get_current_job as _current

        return _current()
    from rq import get_current_job

    return get_current_job()


# ---------------------------------------------------------------------------
# Clustering coalescing
# ---------------------------------------------------------------------------


def _cluster_lock_ttl() -> int:
    """Keep the clustering lock long enough for queued jobs to drain."""
    return max(settings.WORKER_TIMEOUT * 4, 1800)


def clear_clustering_job_state() -> None:
    """Clear clustering lock keys for the active backend."""
    if is_sqlite_backend():
        _clear_clustering_sqlite()
        return
    redis_conn = get_redis_connection()
    redis_conn.delete(CLUSTERING_LOCK_KEY)
    redis_conn.delete(CLUSTERING_JOB_ID_KEY)


def enqueue_clustering_job(*, reason: str) -> dict[str, Any]:
    """Enqueue clustering once, even if multiple workers request it.

    Works with both Redis/RQ and SQLite backends.
    """
    if is_sqlite_backend():
        return _enqueue_clustering_sqlite(reason=reason)

    redis_conn = get_redis_connection()

    if redis_conn.set(CLUSTERING_LOCK_KEY, reason, nx=True, ex=_cluster_lock_ttl()):
        from find_api.workers.jobs import cluster_images

        job = get_task_queue_rq().enqueue(
            cluster_images,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )
        redis_conn.set(CLUSTERING_JOB_ID_KEY, job.id, ex=_cluster_lock_ttl())
        logger.info("Queued clustering job %s (%s)", job.id, reason)
        return {
            "job_id": job.id,
            "message": "Clustering job queued",
            "enqueued": True,
            "status": "queued",
        }

    existing_job_id = redis_conn.get(CLUSTERING_JOB_ID_KEY)
    if existing_job_id:
        job_id = existing_job_id.decode("utf-8")
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            job_status = job.get_status()
        except Exception:  # noqa: BLE001
            clear_clustering_job_state()
        else:
            if job_status not in {"queued", "started", "deferred"}:
                clear_clustering_job_state()
                return enqueue_clustering_job(reason=reason)
            return {
                "job_id": job_id,
                "message": "Clustering job already queued",
                "enqueued": False,
                "status": job_status,
            }

    clear_clustering_job_state()
    return enqueue_clustering_job(reason=reason)
