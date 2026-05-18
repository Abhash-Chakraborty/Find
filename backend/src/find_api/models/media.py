"""
Media model for storing image metadata and embeddings
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
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

    filename = Column(String(255), nullable=False)

    content_type = Column(String(100))

    file_size = Column(Integer)

    liked = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa_text("false"),
    )

    # Status tracking
    status = Column(String(50), default="pending", index=True)
    # pending, processing, indexed, failed

    error_message = Column(Text, nullable=True)

    # NEW: store linked RQ analysis job id
    analysis_job_id = Column(String(255), nullable=True, index=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

    processed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Image metadata
    width = Column(Integer)

    height = Column(Integer)

    exif_json = Column(JSON)

    # AI metadata
    metadata_json = Column(JSON)

    # Clustering
    cluster_id = Column(Integer, index=True, nullable=True)

    # Vector embedding
    vector = Column(Vector(settings.EMBEDDING_DIM))

    def __repr__(self):
        return (
            f"<Media(id={self.id}, "
            f"filename={self.filename}, "
            f"status={self.status})>"
        )