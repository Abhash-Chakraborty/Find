"""Append-only local activity log.

Records privacy-safe events for diagnosing and understanding what changed:
upload/processing outcomes, archive/trash/restore, vault lock/unlock, and
settings updates. ``payload`` must stay small and typed — never image bytes,
embeddings, OCR text, captions, secrets, or raw session tokens (see
services/activity_log.py for the writer that enforces this at call sites).

Rows are written once and never mutated. Both foreign keys use SET NULL (not
CASCADE) so the log outlives the user/media it references, keeping the
history readable after a delete.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class Activity(Base):
    """One append-only activity log entry."""

    __tablename__ = "activity"

    id = Column(Integer, primary_key=True, index=True)

    # Broad grouping for the category filter, e.g. "upload", "media", "vault",
    # "settings".
    category = Column(String(32), nullable=False, index=True)
    # Specific event within the category, e.g. "completed", "failed",
    # "archived", "trashed", "restored", "locked", "unlocked", "updated".
    action = Column(String(32), nullable=False, index=True)

    # Owner scoping (populated in shared mode, null in local mode) — mirrors
    # Media.uploader_user_id.
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Related media, when applicable. Kept even after the media row is gone.
    media_id = Column(
        Integer, ForeignKey("media.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Small, privacy-safe details (e.g. filename, sanitized error, changed
    # setting key). See module docstring for what must never go here.
    payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_activity_user_created", "user_id", "created_at"),)

    def __repr__(self):
        return (
            f"<Activity(id={self.id}, category={self.category}, action={self.action})>"
        )
