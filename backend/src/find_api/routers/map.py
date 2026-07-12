"""Private, local-only map marker endpoints.

Coordinates come from opt-in EXIF extraction. The API never reverse geocodes,
contacts a tile provider, or returns hidden/vault media.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user, scope_media_query
from find_api.core.runtime_profile import load_runtime_preferences
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers.gallery import _public_media_query, build_thumbnail_url

router = APIRouter()


def _map_enabled(db: Session) -> bool:
    return load_runtime_preferences(db).map_enabled


def _marker_query(
    db: Session,
    user: Optional[User],
    *,
    include_archived: bool,
    liked: Optional[bool],
    west: Optional[float],
    south: Optional[float],
    east: Optional[float],
    north: Optional[float],
):
    query = scope_media_query(_public_media_query(db), user).filter(
        Media.deleted_at.is_(None),
        Media.vault_state == "visible",
        Media.latitude.isnot(None),
        Media.longitude.isnot(None),
    )
    if not include_archived:
        query = query.filter(Media.is_archived.is_(False))
    if liked is not None:
        query = query.filter(Media.liked == liked)
    if south is not None:
        query = query.filter(Media.latitude >= south)
    if north is not None:
        query = query.filter(Media.latitude <= north)
    if west is not None and east is not None:
        if west <= east:
            query = query.filter(Media.longitude >= west, Media.longitude <= east)
        else:
            # Bounding boxes crossing the antimeridian wrap around ±180°.
            query = query.filter(or_(Media.longitude >= west, Media.longitude <= east))
    elif west is not None:
        query = query.filter(Media.longitude >= west)
    elif east is not None:
        query = query.filter(Media.longitude <= east)
    return query


@router.get("/map/markers")
def get_map_markers(
    include_archived: bool = False,
    liked: Optional[bool] = None,
    west: Optional[float] = Query(None, ge=-180, le=180),
    south: Optional[float] = Query(None, ge=-90, le=90),
    east: Optional[float] = Query(None, ge=-180, le=180),
    north: Optional[float] = Query(None, ge=-90, le=90),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return scoped media coordinates for local client-side clustering."""
    if not _map_enabled(db):
        return {"enabled": False, "markers": [], "total": 0}

    rows = (
        _marker_query(
            db,
            user,
            include_archived=include_archived,
            liked=liked,
            west=west,
            south=south,
            east=east,
            north=north,
        )
        .order_by(Media.created_at.desc(), Media.id.desc())
        .all()
    )
    markers = [
        {
            "id": media.id,
            "lat": media.latitude,
            "lon": media.longitude,
            "filename": media.filename,
            "created_at": media.created_at.isoformat()
            if media.created_at is not None
            else None,
            "thumbnail_url": build_thumbnail_url(media.id),
            "ratio": round(media.width / media.height, 4)
            if media.width and media.height
            else None,
            "liked": bool(media.liked),
        }
        for media in rows
    ]
    return {"enabled": True, "markers": markers, "total": len(markers)}
