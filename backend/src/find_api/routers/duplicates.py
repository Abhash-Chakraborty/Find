"""GET /api/duplicates — paginated near-duplicate pairs."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.models.user import User
from find_api.services.duplicate_service import (
    clear_duplicate_flag,
    list_duplicate_pairs,
)

router = APIRouter(tags=["duplicates"])


def _scope_user_id(user: Optional[User]) -> Optional[int]:
    """Id a regular user is restricted to, or None for local mode/admin."""
    if user is None or user.role == "admin":
        return None
    return user.id


@router.get("/api/duplicates")
def get_duplicates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return paginated near-duplicate image pairs."""
    return list_duplicate_pairs(
        db=db, page=page, limit=limit, scope_user_id=_scope_user_id(user)
    )


@router.post("/api/image/{media_id}/keep")
def keep_both(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Clear duplicate_of flag — user wants to keep both images."""
    if not clear_duplicate_flag(
        db=db, media_id=media_id, scope_user_id=_scope_user_id(user)
    ):
        raise HTTPException(status_code=404, detail="Image not found")
    return {"status": "ok"}
