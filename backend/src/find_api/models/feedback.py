"""
Feedback models for user corrections and ratings
"""

from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from find_api.core.database import Base


class FeedbackType(str, Enum):
    """Types of feedback users can provide"""

    # Person cluster feedback
    SPLIT = "split"  # Split one person into multiple
    MERGE = "merge"  # Merge two persons
    WRONG_PERSON = "wrong_person"  # Face belongs to different person
    CORRECT = "correct"  # Cluster is correct

    # General feedback
    SEARCH_RATING = "search_rating"  # Rate search result relevance
    CAPTION_RATING = "caption_rating"  # Rate caption accuracy
    OBJECT_RATING = "object_rating"  # Rate object detection accuracy
    CAPTION_CORRECTION = "caption_correction"  # User-edited caption text
    OBJECT_CORRECTION = "object_correction"  # User-edited object labels


class PersonFeedback(Base):
    """
    Stores user feedback about person clusters: splits, merges, corrections.
    Used to improve clustering accuracy over time.
    """

    __tablename__ = "person_feedback"

    # Unique ID for this feedback entry
    id = Column(Integer, primary_key=True, index=True)

    # Type of correction: SPLIT, MERGE, WRONG_PERSON, CORRECT
    feedback_type = Column(String(50), nullable=False, index=True)

    # Person being corrected
    source_person_id = Column(
        Integer,
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # If merging two persons, target person ID
    target_person_id = Column(
        Integer,
        ForeignKey("persons.id", ondelete="SET NULL"),
        nullable=True,
    )

    # JSON array of face IDs affected by this feedback
    # Example: [1, 2, 3] for "these 3 faces should be separate"
    face_ids = Column(JSON, nullable=False)

    # Optional free text reason from user
    user_reason = Column(String(500), nullable=True)

    # Status: pending (not yet applied), applied, rejected
    status = Column(String(20), default="pending", index=True)

    # When feedback was submitted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # When feedback was applied/processed
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return (
            f"<PersonFeedback(id={self.id}, "
            f"type={self.feedback_type}, "
            f"source_person_id={self.source_person_id})>"
        )


class GeneralFeedback(Base):
    """
    Generic feedback for search results, captions, objects, and other entities.
    Supports ratings plus correction metadata that can be used for future
    local personalization or training datasets.
    """

    __tablename__ = "general_feedback"

    # Unique ID
    id = Column(Integer, primary_key=True, index=True)

    # Type: SEARCH_RATING, CAPTION_RATING, OBJECT_RATING, corrections, etc.
    feedback_type = Column(String(50), nullable=False, index=True)

    # Media being rated (optional, for search/caption/object feedback)
    media_id = Column(
        Integer,
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Person being rated (optional, for people grouping feedback)
    person_id = Column(
        Integer,
        ForeignKey("persons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Rating: 1-5 stars
    rating = Column(Integer, nullable=True)

    # Free text reason for the rating
    rating_reason = Column(String(500), nullable=True)

    # JSON metadata (flexible for different feedback types). SQLAlchemy reserves
    # the attribute name `metadata`, so expose it through a safe Python name.
    extra_metadata = Column("metadata", JSON, nullable=True)

    # When feedback was submitted
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<GeneralFeedback(id={self.id}, "
            f"type={self.feedback_type}, "
            f"rating={self.rating})>"
        )
