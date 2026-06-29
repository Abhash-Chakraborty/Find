"""User model for small-team instance sharing."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class User(Base):
    """Represents a registered user on this Find instance.

    In local (single-user) mode no rows exist here. The first row
    created via /api/auth/setup is always the admin.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="member")  # "admin" or "member"
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_users_single_admin",
            "role",
            unique=True,
            postgresql_where=role == "admin",
            sqlite_where=role == "admin",
        ),
    )

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
