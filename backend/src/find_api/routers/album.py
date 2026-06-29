"""Album endpoints — CRUD, membership, cover, and manual ordering.

Scoping mirrors the gallery's media scoping: in local (single-user) mode and
for admins there is no restriction; a regular user in shared mode only sees and
mutates albums they own (``owner_user_id``). Album asset listings reuse the
gallery's browse scoping so archived/trashed media never leak into an album view.

Sharing roles and the activity feed are out of scope here (later stages).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Query as SAQuery, Session

from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user, scope_media_query
from find_api.models.album import Album, AlbumAsset
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers.gallery import (
    _browsable_media_query,
    _serialize_media_item,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---------------------------------------------------------------
class AlbumCreate(BaseModel):
    name: str = Field("Untitled Album", min_length=1, max_length=255)
    description: Optional[str] = None


class AlbumUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cover_media_id: Optional[int] = None


class AlbumAssetsRequest(BaseModel):
    media_ids: list[int] = Field(..., min_length=1, max_length=500)


class AlbumOrderRequest(BaseModel):
    """Ordered list of media ids defining the album's manual order."""

    media_ids: list[int] = Field(..., min_length=1, max_length=2000)


# --- Scoping helpers -------------------------------------------------------
def _scope_albums(query: SAQuery, user: Optional[User]) -> SAQuery:
    """Restrict an album query to those the user may see (IDOR guard)."""
    if user is None or user.role == "admin":
        return query
    return query.filter(Album.owner_user_id == user.id)


def _load_album_or_404(db: Session, album_id: int, user: Optional[User]) -> Album:
    album = _scope_albums(db.query(Album), user).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(404, "Album not found")
    return album


def _album_asset_count(db: Session, album_id: int, user: Optional[User]) -> int:
    # Count only members that actually appear in the album listing — i.e.
    # browsable (not hidden/archived/trashed) and owned by the caller — so the
    # card count never disagrees with what the detail view shows.
    return (
        scope_media_query(_browsable_media_query(db), user)
        .join(AlbumAsset, AlbumAsset.media_id == Media.id)
        .filter(AlbumAsset.album_id == album_id)
        .count()
    )


def _serialize_album(db: Session, album: Album, user: Optional[User]) -> dict:
    return {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "cover_media_id": album.cover_media_id,
        "cover_thumbnail_url": (
            f"/api/image/{album.cover_media_id}/thumbnail"
            if album.cover_media_id
            else None
        ),
        "asset_count": _album_asset_count(db, album.id, user),
        "created_at": album.created_at.isoformat() if album.created_at else None,
        "updated_at": album.updated_at.isoformat() if album.updated_at else None,
    }


# --- CRUD ------------------------------------------------------------------
@router.get("/albums")
def list_albums(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    albums = (
        _scope_albums(db.query(Album), user)
        .order_by(desc(Album.created_at), desc(Album.id))
        .all()
    )
    return {"albums": [_serialize_album(db, a, user) for a in albums], "total": len(albums)}


@router.post("/albums")
def create_album(
    request: AlbumCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    album = Album(
        name=request.name,
        description=request.description,
        owner_user_id=user.id if user is not None else None,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return _serialize_album(db, album, user)


@router.get("/albums/{album_id}")
def get_album(
    album_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    album = _load_album_or_404(db, album_id, user)
    return _serialize_album(db, album, user)


@router.patch("/albums/{album_id}")
def update_album(
    album_id: int,
    request: AlbumUpdate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    album = _load_album_or_404(db, album_id, user)

    if request.name is not None:
        album.name = request.name
    if request.description is not None:
        album.description = request.description
    if request.cover_media_id is not None:
        # Cover must be a member of this album.
        is_member = (
            db.query(AlbumAsset)
            .filter(
                AlbumAsset.album_id == album_id,
                AlbumAsset.media_id == request.cover_media_id,
            )
            .first()
        )
        if not is_member:
            raise HTTPException(400, "Cover image must be a member of the album.")
        album.cover_media_id = request.cover_media_id

    db.commit()
    db.refresh(album)
    return _serialize_album(db, album, user)


@router.delete("/albums/{album_id}")
def delete_album(
    album_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    album = _load_album_or_404(db, album_id, user)
    # Delete membership rows explicitly so behavior is identical on SQLite
    # (tests, no FK enforcement by default) and Postgres (DB-level CASCADE).
    db.query(AlbumAsset).filter(AlbumAsset.album_id == album_id).delete(
        synchronize_session=False
    )
    db.delete(album)
    db.commit()
    return {"message": "Album deleted", "id": album_id}


# --- Membership ------------------------------------------------------------
@router.get("/albums/{album_id}/assets")
def list_album_assets(
    album_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    _load_album_or_404(db, album_id, user)

    # Join membership to browsable media so trashed/archived/hidden never leak,
    # and scope to the caller's own media (IDOR guard) — defense-in-depth so
    # foreign media can't be read back even if a membership row was poisoned.
    rows = (
        scope_media_query(_browsable_media_query(db), user)
        .join(AlbumAsset, AlbumAsset.media_id == Media.id)
        .filter(AlbumAsset.album_id == album_id)
        .order_by(asc(AlbumAsset.position), asc(AlbumAsset.id))
        .all()
    )
    return {
        "items": [_serialize_media_item(m) for m in rows],
        "total": len(rows),
    }


@router.put("/albums/{album_id}/assets")
def add_album_assets(
    album_id: int,
    request: AlbumAssetsRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    _load_album_or_404(db, album_id, user)

    requested = list(dict.fromkeys(request.media_ids))
    # Only add media that exist, are visible to this view, AND belong to the
    # caller (IDOR guard) — without scoping here a user could add another
    # user's media ids to their own album and read the originals/metadata back.
    valid_ids = {
        m.id
        for m in scope_media_query(_browsable_media_query(db), user)
        .filter(Media.id.in_(requested))
        .all()
    }
    existing = {
        row.media_id
        for row in db.query(AlbumAsset.media_id)
        .filter(
            AlbumAsset.album_id == album_id,
            AlbumAsset.media_id.in_(requested),
        )
        .all()
    }

    # Append new members after the current max position.
    max_position = (
        db.query(func.max(AlbumAsset.position))
        .filter(AlbumAsset.album_id == album_id)
        .scalar()
    )
    next_position = (max_position + 1) if max_position is not None else 0

    added: list[int] = []
    skipped: list[int] = []
    for media_id in requested:
        if media_id not in valid_ids or media_id in existing:
            skipped.append(media_id)
            continue
        db.add(
            AlbumAsset(
                album_id=album_id, media_id=media_id, position=next_position
            )
        )
        added.append(media_id)
        next_position += 1

    db.commit()
    return {
        "album_id": album_id,
        "added_ids": added,
        "skipped_ids": skipped,
        "added_count": len(added),
    }


@router.delete("/albums/{album_id}/assets")
def remove_album_assets(
    album_id: int,
    request: AlbumAssetsRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    album = _load_album_or_404(db, album_id, user)

    removed = (
        db.query(AlbumAsset)
        .filter(
            AlbumAsset.album_id == album_id,
            AlbumAsset.media_id.in_(request.media_ids),
        )
        .all()
    )
    removed_ids = [row.media_id for row in removed]
    for row in removed:
        db.delete(row)

    # Clear cover if it was removed.
    if album.cover_media_id in removed_ids:
        album.cover_media_id = None

    db.commit()
    return {
        "album_id": album_id,
        "removed_ids": removed_ids,
        "removed_count": len(removed_ids),
    }


@router.put("/albums/{album_id}/order")
def reorder_album(
    album_id: int,
    request: AlbumOrderRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Set manual ordering from an ordered list of media ids.

    Ids not currently in the album are ignored; members omitted from the list
    keep their relative order after the supplied ones.
    """
    _load_album_or_404(db, album_id, user)

    members = {
        row.media_id: row
        for row in db.query(AlbumAsset)
        .filter(AlbumAsset.album_id == album_id)
        .all()
    }

    position = 0
    seen: set[int] = set()
    for media_id in request.media_ids:
        row = members.get(media_id)
        if row is None or media_id in seen:
            continue
        row.position = position
        seen.add(media_id)
        position += 1

    # Preserve any members not listed, appended in their existing order.
    leftover = sorted(
        (r for mid, r in members.items() if mid not in seen),
        key=lambda r: (r.position, r.id),
    )
    for row in leftover:
        row.position = position
        position += 1

    db.commit()
    return {"album_id": album_id, "ordered_count": len(seen)}
