"""GET /api/duplicates — paginated near-duplicate pairs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from find_api.core.database import get_db

router = APIRouter(tags=["duplicates"])


@router.get("/api/duplicates")
def get_duplicates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated near-duplicate image pairs."""
    offset = (page - 1) * limit

    rows = db.execute(
        text("""
            SELECT
                m.id          AS duplicate_id,
                m.filename   AS duplicate_name,
                m.duplicate_of AS original_id,
                o.filename   AS original_name
            FROM media m
            JOIN media o ON o.id = m.duplicate_of
            WHERE m.duplicate_of IS NOT NULL
            ORDER BY m.id DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    ).fetchall()

    total = db.execute(
        text("SELECT COUNT(*) FROM media WHERE duplicate_of IS NOT NULL")
    ).scalar()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "duplicate_id":   row.duplicate_id,
                "duplicate_name": row.duplicate_name,
                "original_id":    row.original_id,
                "original_name":  row.original_name,
            }
            for row in rows
        ],
    }
    
@router.post("/api/image/{media_id}/keep")
def keep_both(media_id: int, db: Session = Depends(get_db)):
    """Clear duplicate_of flag — user wants to keep both images."""
    db.execute(
        text("UPDATE media SET duplicate_of = NULL WHERE id = :media_id"),
        {"media_id": media_id},
    )
    db.commit()
    return {"status": "ok"}    