"""
Cluster model for storing image clusters
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import deferred
from sqlalchemy.sql import func

from find_api.core.config import settings
from find_api.core.database import Base


class Cluster(Base):
    """Cluster table for storing image clusters"""

    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, index=True)

    # Cluster metadata
    cluster_type = Column(String(50), index=True)
    # Types: face, scene, object, text, general

    label = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)

    # Cluster members
    member_ids = Column(ARRAY(Integer), default=list)
    member_count = Column(Integer, default=0)

    # Centroid vector for assignment
    centroid_vector = deferred(Column(Vector(settings.EMBEDDING_DIM)))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Cluster(id={self.id}, type={self.cluster_type}, members={self.member_count})>"
