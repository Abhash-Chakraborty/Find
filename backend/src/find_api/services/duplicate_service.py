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


def list_duplicate_pairs(
    db: Session,
    page: int,
    limit: int,
    scope_user_id: int | None = None,
) -> dict[str, Any]:
    """Return paginated near-duplicate image pairs.

    When ``scope_user_id`` is provided (shared-mode regular user), only
    pairs whose duplicate image was uploaded by that user are returned.
    """
    offset = (page - 1) * limit
    scope_clause = (
        " AND m.uploader_user_id = :scope_user_id" if scope_user_id is not None else ""
    )
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if scope_user_id is not None:
        params["scope_user_id"] = scope_user_id

    rows = db.execute(
        text(
            f"""
            SELECT
                m.id AS duplicate_id,
                m.filename AS duplicate_name,
                m.duplicate_of AS original_id,
                o.filename AS original_name
            FROM media m
            JOIN media o ON o.id = m.duplicate_of
            WHERE m.duplicate_of IS NOT NULL
            {scope_clause}
            ORDER BY m.id DESC
            LIMIT :limit OFFSET :offset
        """
        ),
        params,
    ).mappings()

    count_params: dict[str, Any] = {}
    if scope_user_id is not None:
        count_params["scope_user_id"] = scope_user_id
    total = db.execute(
        text(
            "SELECT COUNT(*) FROM media m "
            "WHERE m.duplicate_of IS NOT NULL" + scope_clause
        ),
        count_params,
    ).scalar()

    return {
        "total": total or 0,
        "page": page,
        "limit": limit,
        "items": [dict(row) for row in rows],
    }


def clear_duplicate_flag(
    db: Session,
    media_id: int,
    scope_user_id: int | None = None,
) -> bool:
    """Clear a media row duplicate flag when the user keeps both images.

    When ``scope_user_id`` is provided, the update only affects media owned
    by that user; returns False (→ 404) for media owned by someone else.
    """
    scope_clause = (
        " AND uploader_user_id = :scope_user_id" if scope_user_id is not None else ""
    )
    params: dict[str, Any] = {"media_id": media_id}
    if scope_user_id is not None:
        params["scope_user_id"] = scope_user_id
    try:
        result = db.execute(
            text(
                "UPDATE media SET duplicate_of = NULL "
                "WHERE id = :media_id" + scope_clause
            ),
            params,
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        raise
