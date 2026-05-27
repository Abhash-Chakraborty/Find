"""Near-duplicate detection via pgvector cosine similarity."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# images with cosine similarity above this are flagged as near-duplicates
SIMILARITY_THRESHOLD = 0.97


def find_near_duplicate(
    db: Session,
    media_id: int,
    embedding: list[float],
) -> int | None:
    """Query pgvector for a near-duplicate of a newly indexed image."""
    result = db.execute(
        text(
            """
            SELECT id, 1 - (vector <=> CAST(:embedding AS vector)) AS similarity
            FROM media
            WHERE id != :media_id
              AND duplicate_of IS NULL
              AND vector IS NOT NULL
            ORDER BY vector <=> CAST(:embedding AS vector)
            LIMIT 1
        """
        ),
        {
            "embedding": str(embedding),
            "media_id": media_id,
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
    try:
        db.execute(
            text("UPDATE media SET duplicate_of = :dup_of WHERE id = :media_id"),
            {"dup_of": duplicate_of, "media_id": media_id},
        )
        db.commit()
        logger.info("flagged media=%s as duplicate of %s", media_id, duplicate_of)
    except Exception as e:
        db.rollback()
        logger.error("failed to flag duplicate media=%s: %s", media_id, e)
        raise


def list_duplicate_pairs(db: Session, page: int, limit: int) -> dict[str, Any]:
    """Return paginated near-duplicate image pairs."""
    offset = (page - 1) * limit
    rows = db.execute(
        text(
            """
            SELECT
                m.id AS duplicate_id,
                m.filename AS duplicate_name,
                m.duplicate_of AS original_id,
                o.filename AS original_name
            FROM media m
            JOIN media o ON o.id = m.duplicate_of
            WHERE m.duplicate_of IS NOT NULL
            ORDER BY m.id DESC
            LIMIT :limit OFFSET :offset
        """
        ),
        {"limit": limit, "offset": offset},
    ).mappings()

    total = db.execute(
        text("SELECT COUNT(*) FROM media WHERE duplicate_of IS NOT NULL")
    ).scalar()

    return {
        "total": total or 0,
        "page": page,
        "limit": limit,
        "items": [dict(row) for row in rows],
    }


def clear_duplicate_flag(db: Session, media_id: int) -> bool:
    """Clear a media row duplicate flag when the user keeps both images."""
    try:
        result = db.execute(
            text("UPDATE media SET duplicate_of = NULL WHERE id = :media_id"),
            {"media_id": media_id},
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        raise
