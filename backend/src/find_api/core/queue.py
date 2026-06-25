"""Queue helpers for background jobs."""

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
FEEDBACK_LOCK_KEY = "find:feedback-ranking:queued"
FEEDBACK_JOB_ID_KEY = "find:feedback-ranking:job-id"


def get_redis_connection() -> Redis:
    """Create a Redis connection for queue operations."""
    return Redis.from_url(settings.REDIS_URL)


def get_task_queue(name: str = DEFAULT_QUEUE_NAME) -> Queue:
    """Create an RQ queue instance."""
    return Queue(name, connection=get_redis_connection())


def _cluster_lock_ttl() -> int:
    """Keep the clustering lock long enough for queued jobs to drain."""
    return max(settings.WORKER_TIMEOUT * 4, 1800)


def clear_clustering_job_state() -> None:
    """Clear Redis keys used to coalesce clustering jobs."""
    redis_conn = get_redis_connection()
    redis_conn.delete(CLUSTERING_LOCK_KEY)
    redis_conn.delete(CLUSTERING_JOB_ID_KEY)


def clear_feedback_ranking_job_state() -> None:
    """Clear Redis keys used to coalesce feedback ranking jobs."""
    redis_conn = get_redis_connection()
    redis_conn.delete(FEEDBACK_LOCK_KEY)
    redis_conn.delete(FEEDBACK_JOB_ID_KEY)


def enqueue_clustering_job(*, reason: str) -> dict[str, Any]:
    """Enqueue clustering once, even if multiple workers request it."""
    redis_conn = get_redis_connection()
    existing_job_id = redis_conn.get(CLUSTERING_JOB_ID_KEY)

    if redis_conn.set(CLUSTERING_LOCK_KEY, reason, nx=True, ex=_cluster_lock_ttl()):
        from find_api.workers.jobs import cluster_images

        job = get_task_queue().enqueue(
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


def enqueue_feedback_ranking_job(reason: str) -> dict[str, Any]:
    """Enqueue feedback ranking update job only once."""
    redis_conn = get_redis_connection()
    existing_job_id = redis_conn.get(FEEDBACK_JOB_ID_KEY)

    if redis_conn.set(FEEDBACK_LOCK_KEY, reason, nx=True, ex=300):
        from find_api.workers.jobs import process_feedback_ranking

        job = get_task_queue().enqueue(
            process_feedback_ranking,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )

        redis_conn.set(FEEDBACK_JOB_ID_KEY, job.id, ex=300)

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
        job_id = existing_job_id.decode("utf-8")
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            job_status = job.get_status()
        except Exception:  # noqa: BLE001
            clear_feedback_ranking_job_state()
        else:
            if job_status not in {"queued", "started", "deferred"}:
                clear_feedback_ranking_job_state()
                return enqueue_feedback_ranking_job(reason=reason)
            return {
                "job_id": job_id,
                "message": "Feedback ranking job already queued",
                "enqueued": False,
                "status": job_status,
            }

    clear_feedback_ranking_job_state()
    return enqueue_feedback_ranking_job(reason=reason)
