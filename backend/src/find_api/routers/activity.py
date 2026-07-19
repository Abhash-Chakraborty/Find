"""Local activity log — read history and manage retention.

Rows are written elsewhere (see services/activity_log.py) at the point of
each state change; this router only reads and prunes them.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user, scope_activity_query
from find_api.models.activity import Activity
from find_api.models.user import User

router = APIRouter()


class ActivityPurgeResponse(BaseModel):
    """Summary of a clear/purge request."""

    message: str
    deleted_count: int


def _serialize_activity(entry: Activity) -> dict:
    return {
        "id": entry.id,
        "category": entry.category,
        "action": entry.action,
        "user_id": entry.user_id,
        "media_id": entry.media_id,
        "payload": entry.payload,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@router.get("/activity")
def list_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = Query(None, description="e.g. 'upload', 'vault'"),
    action: Optional[str] = Query(None, description="e.g. 'completed', 'failed'"),
    media_id: Optional[int] = Query(None, description="Filter to one asset's history"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """List activity log entries, newest first."""
    query = scope_activity_query(db.query(Activity), user)
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
    items = [_serialize_activity(row) for row in rows]
    page = (skip // limit) + 1 if limit else 1
    return {"items": items, "total": total, "skip": skip, "page": page, "limit": limit}


@router.post("/activity/clear", response_model=ActivityPurgeResponse)
def clear_activity(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Delete every activity row the current user can see."""
    deleted = scope_activity_query(db.query(Activity), user).delete(
        synchronize_session=False
    )
    db.commit()
    return {"message": "Activity cleared", "deleted_count": deleted}


@router.post("/activity/purge", response_model=ActivityPurgeResponse)
def purge_expired_activity(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Delete activity rows older than the retention window.

    Mirrors ``POST /trash/purge``: age-bounded, intended for a scheduled or
    manual auto-purge. ``ACTIVITY_RETENTION_DAYS=0`` disables it (no-op).
    """
    retention_days = settings.ACTIVITY_RETENTION_DAYS
    if retention_days <= 0:
        return {
            "message": "Auto-purge disabled (ACTIVITY_RETENTION_DAYS=0)",
            "deleted_count": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = scope_activity_query(
        db.query(Activity).filter(Activity.created_at < cutoff), user
    ).delete(synchronize_session=False)
    db.commit()
    return {
        "message": f"Purged activity older than {retention_days} days",
        "deleted_count": deleted,
    }
