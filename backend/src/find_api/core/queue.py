"""Queue helpers for background jobs — supports both Redis/RQ and SQLite backends."""

from __future__ import annotations

import logging
from typing import Any

from find_api.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_NAME = "default"
CLUSTERING_LOCK_KEY = "find:clustering:queued"
CLUSTERING_JOB_ID_KEY = "find:clustering:job-id"
FEEDBACK_LOCK_KEY = "find:feedback-ranking:queued"
FEEDBACK_JOB_ID_KEY = "find:feedback-ranking:job-id"

# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

_BACKEND: Any = None


def _get_backend():
    """Lazily import and return the active queue backend instance."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    if settings.QUEUE_MODE == "sqlite":
        from find_api.core.sqlite_queue import SqliteQueue

        _BACKEND = SqliteQueue()
        _get_backend.mode = "sqlite"
    else:
        from redis import Redis
        from rq import Queue

        _get_backend.redis_conn = Redis.from_url(settings.REDIS_URL)
        _BACKEND = Queue(DEFAULT_QUEUE_NAME, connection=_get_backend.redis_conn)
        _get_backend.mode = "redis"

    return _BACKEND


_get_backend.mode = "redis"
_get_backend.redis_conn = None

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_redis_connection():
    """Return the Redis connection (works only in Redis mode)."""
    _get_backend()
    if _get_backend.mode != "redis":
        raise RuntimeError("Redis connection is only available in redis queue mode")
    return _get_backend.redis_conn


def get_task_queue(name: str = DEFAULT_QUEUE_NAME):
    """Return a queue-like object with an ``enqueue`` method.

    In Redis mode returns an ``rq.Queue``; in SQLite mode returns a
    ``SqliteQueue``.
    """
    if settings.QUEUE_MODE == "sqlite":
        return _get_backend()

    from rq import Queue

    return Queue(name, connection=get_redis_connection())


RQ_CONTROL_KWARGS = frozenset(
    {"job_timeout", "result_ttl", "ttl", "failure_ttl", "depends_on"}
)


def enqueue_job(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Enqueue a job, returning a proxy with at least ``.id``.

    Accepts the same arguments as ``rq.Queue.enqueue``.  Extra kwargs
    (``job_timeout``, ``result_ttl``, …) are forwarded in Redis mode and
    stripped in SQLite mode.
    """
    backend = _get_backend()
    if _get_backend.mode == "sqlite":
        sqlite_kwargs = {k: v for k, v in kwargs.items() if k not in RQ_CONTROL_KWARGS}
        return backend.enqueue_call(func, *args, **sqlite_kwargs)
    else:
        return backend.enqueue(func, *args, **kwargs)


def get_job(job_id: str) -> Any:
    """Fetch a job by id across either backend.

    Returns a proxy with ``.id``, ``.get_status()``, ``.meta``,
    ``.created_at``, ``.started_at``, ``.ended_at`` / ``.completed_at``,
    ``.is_finished``, ``.is_failed``, and ``.result``.
    """
    backend = _get_backend()
    if _get_backend.mode == "sqlite":
        return backend.get_job(job_id)
    else:
        from rq.job import Job

        return Job.fetch(job_id, connection=_get_backend.redis_conn)


# ---------------------------------------------------------------------------
# Clustering coalescing
# ---------------------------------------------------------------------------


def _cluster_lock_ttl() -> int:
    """Keep the clustering lock long enough for queued jobs to drain."""
    return max(settings.WORKER_TIMEOUT * 4, 1800)


def clear_clustering_job_state() -> None:
    """Clear keys used to coalesce clustering jobs."""
    backend = _get_backend()
    if _get_backend.mode == "redis":
        _get_backend.redis_conn.delete(CLUSTERING_LOCK_KEY)
        _get_backend.redis_conn.delete(CLUSTERING_JOB_ID_KEY)
    else:
        backend.release_clustering_lock(CLUSTERING_LOCK_KEY)


def _get_existing_clustering_job_id() -> str | None:
    """Return a previously-queued clustering job id, if any."""
    backend = _get_backend()
    if _get_backend.mode == "redis":
        val = _get_backend.redis_conn.get(CLUSTERING_JOB_ID_KEY)
        if val:
            return val.decode("utf-8")
        return None
    else:
        jobs = backend.list_active()
        for j in jobs:
            if "cluster_images" in j.type or "clustering" in j.type:
                return j.id
        return None


def _set_clustering_lock(*, reason: str) -> bool:
    """Acquire the clustering lock.

    Returns True if this caller won the lock.
    """
    backend = _get_backend()
    if _get_backend.mode == "redis":
        return bool(
            _get_backend.redis_conn.set(
                CLUSTERING_LOCK_KEY, reason, nx=True, ex=_cluster_lock_ttl()
            )
        )
    else:
        return backend.acquire_clustering_lock(
            CLUSTERING_LOCK_KEY, reason, _cluster_lock_ttl()
        )


def _save_clustering_job_id(job_id: str) -> None:
    """Persist a clustering job id."""
    if _get_backend.mode == "redis":
        _get_backend.redis_conn.set(
            CLUSTERING_JOB_ID_KEY, job_id, ex=_cluster_lock_ttl()
        )


def clear_feedback_ranking_job_state() -> None:
    """Clear keys used to coalesce feedback ranking jobs."""
    backend = _get_backend()
    if _get_backend.mode == "redis":
        _get_backend.redis_conn.delete(FEEDBACK_LOCK_KEY)
        _get_backend.redis_conn.delete(FEEDBACK_JOB_ID_KEY)
    else:
        backend.release_clustering_lock(FEEDBACK_LOCK_KEY)


def enqueue_clustering_job(*, reason: str) -> dict[str, Any]:
    """Enqueue clustering once, even if multiple callers request it."""
    from find_api.workers.jobs import cluster_images

    if not _set_clustering_lock(reason=reason):
        existing_id = _get_existing_clustering_job_id()
        if existing_id:
            try:
                job = get_job(existing_id)
                job_status = job.get_status()
            except Exception:  # noqa: BLE001
                clear_clustering_job_state()
            else:
                if job_status not in {"queued", "started", "deferred", "running"}:
                    clear_clustering_job_state()
                    return enqueue_clustering_job(reason=reason)
                return {
                    "job_id": existing_id,
                    "message": "Clustering job already queued",
                    "enqueued": False,
                    "status": job_status,
                }

        clear_clustering_job_state()
        return enqueue_clustering_job(reason=reason)

    job = enqueue_job(
        cluster_images,
        job_timeout=settings.WORKER_TIMEOUT,
        result_ttl=300,
    )
    _save_clustering_job_id(job.id)
    logger.info("Queued clustering job %s (%s)", job.id, reason)
    return {
        "job_id": job.id,
        "message": "Clustering job queued",
        "enqueued": True,
        "status": "queued",
    }


def enqueue_feedback_ranking_job(reason: str) -> dict[str, Any]:
    """Enqueue feedback ranking update job only once."""
    from find_api.workers.jobs import process_feedback_ranking

    backend = _get_backend()
    ttl_seconds = 300
    existing_job_id: str | None = None
    if _get_backend.mode == "redis":
        existing_job_id_bytes = _get_backend.redis_conn.get(FEEDBACK_JOB_ID_KEY)
        if existing_job_id_bytes:
            existing_job_id = existing_job_id_bytes.decode("utf-8")
        lock_acquired = bool(
            _get_backend.redis_conn.set(
                FEEDBACK_LOCK_KEY,
                reason,
                nx=True,
                ex=ttl_seconds,
            )
        )
    else:
        lock_acquired = backend.acquire_clustering_lock(
            FEEDBACK_LOCK_KEY,
            reason,
            ttl_seconds,
        )
        for job in backend.list_active():
            if "process_feedback_ranking" in job.type:
                existing_job_id = job.id
                break

    if lock_acquired:
        job = enqueue_job(
            process_feedback_ranking,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )

        if _get_backend.mode == "redis":
            _get_backend.redis_conn.set(FEEDBACK_JOB_ID_KEY, job.id, ex=ttl_seconds)

        logger.info(
            "Queued feedback ranking job %s (%s)",
            job.id,
            reason,
        )

        return {
            "job_id": job.id,
            "message": "Feedback ranking job queued",
            "enqueued": True,
            "status": "queued",
        }

    if existing_job_id:
        try:
            job = get_job(existing_job_id)
            if job is None:
                raise LookupError(f"Feedback ranking job {existing_job_id} not found")
            job_status = job.get_status()
        except Exception:  # noqa: BLE001
            clear_feedback_ranking_job_state()
        else:
            if job_status not in {"queued", "started", "deferred", "running"}:
                clear_feedback_ranking_job_state()
                return enqueue_feedback_ranking_job(reason=reason)
            return {
                "job_id": existing_job_id,
                "message": "Feedback ranking job already queued",
                "enqueued": False,
                "status": job_status,
            }

    clear_feedback_ranking_job_state()
    return enqueue_feedback_ranking_job(reason=reason)
