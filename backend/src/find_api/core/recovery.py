"""Recovery helpers for abandoned background analysis jobs.

Works with both the Redis/RQ and SQLite queue backends.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import SessionLocal
from find_api.core.queue import get_job
from find_api.models.media import Media

logger = logging.getLogger(__name__)

RECOVERY_ERROR_MESSAGE = (
    "Analysis job timed out or was abandoned before completion. "
    "Retry analysis to process this image again."
)
INCOMPLETE_JOB_ERROR_MESSAGE = (
    "Analysis job ended before media processing completed. "
    "Retry analysis to process this image again."
)
ACTIVE_JOB_STATUSES = {"queued", "started", "deferred", "scheduled", "running"}
FAILED_JOB_STATUSES = {"failed", "stopped", "canceled"}
RECOVERY_INTERVAL_SECONDS = 60


def reconcile_abandoned_analysis_jobs(db: Session, **kwargs: Any) -> int:
    """Reconcile pending/processing media with their active jobs.

    Media rows keep the current analysis job id so healthy queued/started
    work can remain active while failed jobs, completed-without-result
    jobs, and missing stale jobs move back to a truthful failed state.

    Works with both Redis/RQ and SQLite queue backends.
    """
    timeout_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.WORKER_TIMEOUT * 2
    )

    active_media = (
        db.query(Media).filter(Media.status.in_(["pending", "processing"])).all()
    )

    reconciled = 0
    for media in active_media:
        job_status = _get_job_status(media.analysis_job_id)

        if job_status in ACTIVE_JOB_STATUSES:
            continue
        if job_status in FAILED_JOB_STATUSES:
            _mark_failed(media, RECOVERY_ERROR_MESSAGE)
            reconciled += 1
            continue
        if job_status == "finished":
            _mark_failed(media, INCOMPLETE_JOB_ERROR_MESSAGE)
            reconciled += 1
            continue
        if job_status == "completed":
            _mark_failed(media, INCOMPLETE_JOB_ERROR_MESSAGE)
            reconciled += 1
            continue

        last_activity = media.updated_at or media.created_at
        if last_activity and _as_utc(last_activity) < timeout_at:
            _mark_failed(media, RECOVERY_ERROR_MESSAGE)
            reconciled += 1

    if reconciled:
        db.commit()

    return reconciled


async def run_analysis_recovery_loop() -> None:
    """Periodically reconcile analysis jobs while the API is running."""
    while True:
        await asyncio.sleep(RECOVERY_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            reconciled = reconcile_abandoned_analysis_jobs(db)
            if reconciled:
                logger.info("Recovered %s abandoned analysis jobs", reconciled)
        except Exception:  # noqa: BLE001
            logger.exception("Analysis job reconciliation failed")
        finally:
            db.close()


def _get_job_status(job_id: str | None) -> str | None:
    if not job_id:
        return None
    job = get_job(job_id)
    if job is None:
        return None
    return job.get_status()


def _mark_failed(media: Media, message: str) -> None:
    media.status = "failed"
    media.error_message = message
    media.processed_at = None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
