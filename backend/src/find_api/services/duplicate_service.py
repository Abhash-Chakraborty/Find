"""Near-duplicate detection via pgvector cosine similarity."""

from __future__ import annotations
from typing import Optional
import logging
from tarfile import NUL
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# images with cosine similarity above this are flagged as near-duplicates
SIMILARITY_THRESHOLD = 0.97

def find_near_duplicate(
    db: Session,
    media_id: int,
    embedding: list[float],
    user_id: Optional[int] = None,  
) -> Optional[int]:
    """Query pgvector for a near-duplicate of a newly indexed image."""
    result = db.execute(
        text("""
            SELECT id, 1 - (vector <=> :embedding::vector) AS similarity
            FROM media
            WHERE id != :media_id
              AND duplicate_of IS NULL
              AND vector IS NOT NULL
              AND (:user_id IS NULL OR user_id = :user_id)
            ORDER BY vector <=> :embedding::vector
            LIMIT 1
        """),
        {
            "embedding": str(embedding),
            "media_id": media_id,
            "user_id": user_id,
        },
    ).fetchone()

    if result is None:
        return None

    similar_id, similarity = result
    if similarity >= SIMILARITY_THRESHOLD:
        return similar_id
    return None

def flag_as_duplicate(db: Session, media_id: int, duplicate_of: int) -> None:
    """Mark media_id as a near-duplicate of duplicate_of."""
    db.execute(
        text("UPDATE media SET duplicate_of = :dup_of WHERE id = :media_id"),
        {"dup_of": duplicate_of, "media_id": media_id},
    )
    db.commit()
    logger.info("flagged media=%s as duplicate of %s", media_id, duplicate_of)