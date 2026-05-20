"""
Face model for storing detected faces and their embeddings
"""

from sqlalchemy import Column, Integer, Float, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from find_api.core.database import Base

FACE_EMBEDDING_DIM = 512


class Face(Base):
    """
    Stores every face detected in every image.
    One image can have many faces (e.g. a group photo).
    """

    __tablename__ = "faces"

    # Primary key - unique ID for each face
    id = Column(Integer, primary_key=True, index=True)

    # Which image this face belongs to
    # ForeignKey means: this must match an id in the 'media' table
    media_id = Column(
        Integer,
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Where in the image the face was found
    # Stored as JSON: {"x1": 10, "y1": 20, "x2": 100, "y2": 120}
    bounding_box = Column(JSON, nullable=False)

    # The 512-number fingerprint of this face
    # Similar faces will have similar numbers
    embedding = Column(Vector(FACE_EMBEDDING_DIM), nullable=True)

    # How confident the AI is that this is a real face (0.0 to 1.0)
    confidence = Column(Float, nullable=False, default=0.0)

    # Which person group this face belongs to (set after clustering)
    # Nullable because we don't know the person yet when first detected
    person_id = Column(
        Integer,
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # When this face was detected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<Face(id={self.id}, "
            f"media_id={self.media_id}, "
            f"confidence={self.confidence:.2f}, "
            f"person_id={self.person_id})>"
        )
