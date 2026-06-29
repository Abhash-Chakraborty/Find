"""Join request model for the admin approval workflow."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class JoinRequest(Base):
    """Tracks a prospective user's request to join this instance.

    The password is hashed at request time so plaintext credentials
    are never stored, even temporarily.
    """

    __tablename__ = "join_requests"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), nullable=False)
    display_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    invite_token_id = Column(
        Integer,
        ForeignKey("invite_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(20), nullable=False, default="pending")
    reviewed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<JoinRequest(id={self.id}, status={self.status})>"
