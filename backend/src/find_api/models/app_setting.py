"""Persisted application settings (key/value).

A tiny key/value store for runtime-adjustable preferences that should survive
a restart without editing ``.env`` — currently the hardware-acceleration mode
chosen in the settings panel. Kept as key/value (not a typed column per
setting) so adding a future setting needs no migration; values are stored as
strings and validated at the API boundary.

Scope note: this persists the *preference*. The API process reads it back
immediately (see routers/config.py), so the settings panel reflects the saved
choice. Propagating a changed value into already-running ML worker processes is
separate cross-process work and is intentionally out of scope here.
"""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func

from find_api.core.database import Base


class AppSetting(Base):
    """One persisted setting as a key/value pair."""

    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<AppSetting(key={self.key!r}, value={self.value!r})>"
