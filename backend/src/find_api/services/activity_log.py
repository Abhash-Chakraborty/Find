"""Best-effort writer for the local activity log (see models/activity.py).

Called after the state change it describes has already committed, so a
failed write here can never roll back real work — it only means one
diagnostic row is missing. Payloads must stay small and privacy-safe: no
image bytes, embeddings, OCR text, captions, secrets, or raw session tokens.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

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
