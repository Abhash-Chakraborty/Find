"""GET /api/duplicates — paginated near-duplicate pairs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.services.duplicate_service import (
    clear_duplicate_flag,
    list_duplicate_pairs,
)

router = APIRouter(tags=["duplicates"])


@router.get("/api/duplicates")
def get_duplicates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated near-duplicate image pairs."""
    return list_duplicate_pairs(db=db, page=page, limit=limit)


@router.post("/api/image/{media_id}/keep")
def keep_both(media_id: int, db: Session = Depends(get_db)):
    """Clear duplicate_of flag — user wants to keep both images."""
    if not clear_duplicate_flag(db=db, media_id=media_id):
        raise HTTPException(status_code=404, detail="Image not found")
    return {"status": "ok"}
