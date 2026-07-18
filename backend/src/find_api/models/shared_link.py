"""Shared link model — public, capability-URL access to a single album.

Security design (intentionally diverges from the reference, which stores
share-link passwords in plaintext):

- The access ``key`` is a 256-bit CSPRNG token. Only its SHA-256 hash is
  stored (``key_hash``); the raw key lives solely in the share URL, mirroring
  Find's session/invite token handling. A DB leak therefore yields no usable
  links.
- An optional password is stored as a bcrypt hash (``password_hash``), never
  plaintext, and verified in constant time.
- ``expires_at`` is enforced server-side on every public request.
- A link grants access to EXACTLY one album's assets — never the owner's
  whole library.

Partner sharing (directional library sharing between users) is deferred; it
needs multi-user semantics beyond this slice.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text as sa_text,
)
from sqlalchemy.sql import func

from find_api.core.database import Base


class SharedLink(Base):
    """A capability-URL granting public read access to one album."""

    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, index=True)

    # SHA-256 hex of the raw key. The raw key is never stored.
    key_hash = Column(String(64), unique=True, nullable=False, index=True)

    album_id = Column(
        Integer,
        ForeignKey("albums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Owner of the link; null in local mode, set in shared mode for scoping.
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional bcrypt password hash (never plaintext).
    password_hash = Column(String(255), nullable=True)

    description = Column(String(500), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Whether viewers may fetch original files (vs thumbnails only).
    allow_download = Column(
        Boolean, nullable=False, default=True, server_default=sa_text("true")
    )
    # Whether EXIF metadata is exposed to viewers.
    show_exif = Column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SharedLink(id={self.id}, album={self.album_id})>"
