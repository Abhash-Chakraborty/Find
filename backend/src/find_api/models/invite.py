"""Invite token model for the join flow."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class InviteToken(Base):
    """A single-use, short-lived invite token created by the admin.

    The raw token value is returned to the admin once and never stored.
    Only the SHA-256 hash is persisted so a database compromise does
    not leak usable invite codes.
    """

    __tablename__ = "invite_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<InviteToken(id={self.id}, is_used={self.is_used})>"
