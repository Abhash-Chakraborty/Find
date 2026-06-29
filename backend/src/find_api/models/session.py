"""Server-side session model for token-based authentication."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class AuthSession(Base):
    """Each login creates a row here. Logout or expiry removes it.

    The raw token is sent to the client as a bearer token. We only
    store the SHA-256 hash so a database leak does not compromise
    active sessions.
    """

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AuthSession(id={self.id}, user_id={self.user_id})>"
