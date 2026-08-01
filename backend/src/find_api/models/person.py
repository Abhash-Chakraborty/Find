"""
Person model for storing person groups (face clusters)
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from find_api.core.database import Base


class Person(Base):
    """
    Represents a group of faces that belong to the same person.

    A Person is created automatically by the clustering algorithm.
    The user can then give it a name like 'Alice' or 'Dad'.

    One Person → many Faces (stored in the faces table via person_id)
    """

    __tablename__ = "persons"

    # Unique ID for each person group
    id = Column(Integer, primary_key=True, index=True)

    # Name given by the user e.g. 'Alice', 'Dad'
    # Starts as None - user fills this in later from the UI
    name = Column(String(255), nullable=True)

    # When this person group was created by clustering
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # When the user last updated the name
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Person(id={self.id}, name={self.name!r})>"
