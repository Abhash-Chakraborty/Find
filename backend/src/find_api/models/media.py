"""
Media model for storing image metadata and embeddings
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Text,
    JSON,
    Boolean,
    text as sa_text,
)
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from find_api.core.database import Base
from find_api.core.config import settings


class Media(Base):
    """Media table for storing image information"""

    __tablename__ = "media"

    id = Column(Integer, primary_key=True, index=True)
    file_hash = Column(String(64), unique=True, index=True, nullable=False)
    minio_key = Column(String(255), nullable=False)
    thumbnail_key = Column(String(255), nullable=True)
    thumbnail_content_type = Column(String(100), nullable=True)
    thumbnail_size = Column(Integer, nullable=True)
    thumbnail_width = Column(Integer, nullable=True)
    thumbnail_height = Column(Integer, nullable=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100))
    file_size = Column(Integer)
    liked = Column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    is_hidden = Column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )

    # Status tracking
    status = Column(String(50), default="pending", index=True)
    # Status values: pending, processing, indexed, failed
    analysis_job_id = Column(String(64), nullable=True, index=True)

    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Image metadata
    width = Column(Integer)
    height = Column(Integer)
    exif_json = Column(JSON)  # EXIF data

    # AI-generated metadata
    metadata_json = Column(JSON)  # Contains: caption, objects, ocr_text, faces, etc.

    # Clustering
    cluster_id = Column(Integer, index=True, nullable=True)
    # Near-duplicate detection
    duplicate_of = Column(
        Integer,
        ForeignKey("media.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Uploader tracking (populated in shared mode, null in local mode)
    uploader_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Vector embedding for semantic search
    vector = Column(Vector(settings.EMBEDDING_DIM))

    def __repr__(self):
        return f"<Media(id={self.id}, filename={self.filename}, status={self.status})>"
