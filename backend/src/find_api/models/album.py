"""
Album models — collections of media with a cover and manual ordering.

`Album` holds metadata + cover; `AlbumAsset` is the membership join with a
`position` for manual ordering. Album sharing (roles) and the activity feed are
intentionally out of scope here (Stage 4.3+); this is CRUD + membership only.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.sql import func
from find_api.core.database import Base


class Album(Base):
    """A named collection of media."""

    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, default="Untitled Album")
    description = Column(Text, nullable=True)

    # Cover image; cleared (not deleted) if the chosen media is removed.
    cover_media_id = Column(
        Integer,
        ForeignKey("media.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Owner; null in local (single-user) mode, set in shared mode for scoping
    # (mirrors media.uploader_user_id).
    owner_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Album(id={self.id}, name={self.name!r})>"


class AlbumAsset(Base):
    """Membership of a media item in an album, with manual ordering."""

    __tablename__ = "album_assets"

    id = Column(Integer, primary_key=True, index=True)
    album_id = Column(
        Integer,
        ForeignKey("albums.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_id = Column(
        Integer,
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Manual ordering within the album (ascending). Ties broken by id.
    position = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("album_id", "media_id", name="uq_album_asset"),
        Index("ix_album_assets_album_position", "album_id", "position"),
    )

    def __repr__(self):
        return f"<AlbumAsset(album={self.album_id}, media={self.media_id})>"
