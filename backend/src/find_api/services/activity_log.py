"""Best-effort writer for the local activity log (see models/activity.py).

Called after the state change it describes has already committed, so a
failed write here can never roll back real work — it only means one
diagnostic row is missing. Payloads must stay small and privacy-safe: no
image bytes, embeddings, OCR text, captions, secrets, or raw session tokens.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from find_api.core.dependencies import scope_activity_query
from find_api.models.activity import Activity

logger = logging.getLogger(__name__)


def record_activity(
    db: Session,
    category: str,
    action: str,
    *,
    user_id: Optional[int] = None,
    media_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    """Append one activity row in its own transaction. Never raises."""
    try:
        db.add(
            Activity(
                category=category,
                action=action,
                user_id=user_id,
                media_id=media_id,
                payload=payload,
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Failed to record activity %s.%s: %s", category, action, exc)


def _scoped(db: Session, user, *, before: Optional[datetime] = None):
    """Base query for the rows *user* is allowed to see."""
    query = db.query(Activity)
    if before is not None:
        query = query.filter(Activity.created_at < before)
    return scope_activity_query(query, user)


def list_activity(
    db: Session,
    user,
    *,
    skip: int = 0,
    limit: int = 50,
    category: Optional[str] = None,
    action: Optional[str] = None,
    media_id: Optional[int] = None,
) -> tuple[list[Activity], int]:
    """Return one owner-scoped page of activity (newest first) and the total."""
    query = _scoped(db, user)
    if category:
        query = query.filter(Activity.category == category)
    if action:
        query = query.filter(Activity.action == action)
    if media_id is not None:
        query = query.filter(Activity.media_id == media_id)

    total = query.count()
    rows = (
        query.order_by(Activity.created_at.desc(), Activity.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows, total


def clear_activity(db: Session, user) -> int:
    """Delete every row *user* can see. Returns the number deleted."""
    deleted = _scoped(db, user).delete(synchronize_session=False)
    db.commit()
    return deleted


def purge_expired_activity(db: Session, user, retention_days: int) -> int:
    """Delete rows older than the retention window. 0 disables (no-op)."""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = _scoped(db, user, before=cutoff).delete(synchronize_session=False)
    db.commit()
    return deleted
