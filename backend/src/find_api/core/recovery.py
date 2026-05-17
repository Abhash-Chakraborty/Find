"""Recovery helpers for abandoned background analysis jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.models.media import Media

RECOVERY_ERROR_MESSAGE = (
    "Analysis job timed out or was abandoned before completion. "
    "Retry analysis to process this image again."
)


def reconcile_abandoned_analysis_jobs(db: Session) -> int:
    """Mark stale pending/processing media as failed.

    RQ job metadata can disappear after worker crashes, Redis restarts, or result TTL
    expiry. Media rows should not stay pending/processing forever, so this helper
    moves old in-progress rows back to a truthful failed state.
    """
    timeout_at = datetime.now(timezone.utc) - timedelta(
        seconds=settings.WORKER_TIMEOUT * 2
    )

    stale_media = (
        db.query(Media)
        .filter(Media.status.in_(["pending", "processing"]))
        .filter(Media.created_at < timeout_at)
        .all()
    )

    for media in stale_media:
        media.status = "failed"
        media.error_message = RECOVERY_ERROR_MESSAGE
        media.processed_at = None

    if stale_media:
        db.commit()

    return len(stale_media)