"""Shared-link endpoints — management (owner) + public (capability URL).

Security model (see also models/shared_link.py):

- Management routes (`/shared-links*`) require the normal user dependency and
  are owner-scoped (IDOR guard), mirroring albums.
- Public routes (`/public/shared/...`) take the raw key from the URL, hash it,
  and look up by hash. They enforce ``expires_at`` server-side, require the
  password (if set) verified in constant time, and expose ONLY the linked
  album's browsable assets — never the owner's wider library. Original-file
  access is gated on ``allow_download``; EXIF on ``show_exif``.

We deliberately do NOT replicate the reference's plaintext password storage.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Query as SAQuery, Session

from find_api.core.auth import (
    hash_password,
    hash_token,
    verify_password_constant_time,
)
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.core.storage import get_file
from find_api.models.album import Album, AlbumAsset
from find_api.models.media import Media
from find_api.models.shared_link import SharedLink
from find_api.models.user import User
from find_api.routers.gallery import _browsable_media_query

import secrets

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schemas ---------------------------------------------------------------
class SharedLinkCreate(BaseModel):
    album_id: int
    password: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = None
    allow_download: bool = True
    show_exif: bool = False


class SharedLinkUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = None
    allow_download: Optional[bool] = None
    show_exif: Optional[bool] = None
    # "" clears the password; a non-empty value sets a new one; None leaves it.
    password: Optional[str] = Field(None, max_length=128)


class PublicUnlockRequest(BaseModel):
    password: Optional[str] = None


# --- Helpers ---------------------------------------------------------------
def _scope_links(query: SAQuery, user: Optional[User]) -> SAQuery:
    if user is None or user.role == "admin":
        return query
    return query.filter(SharedLink.owner_user_id == user.id)


def _load_owned_link_or_404(
    db: Session, link_id: int, user: Optional[User]
) -> SharedLink:
    link = (
        _scope_links(db.query(SharedLink), user)
        .filter(SharedLink.id == link_id)
        .first()
    )
    if not link:
        raise HTTPException(404, "Shared link not found")
    return link


def _is_expired(link: SharedLink) -> bool:
    if link.expires_at is None:
        return False
    expires = link.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= expires


def _serialize_link(link: SharedLink, *, include_key: Optional[str] = None) -> dict:
    data = {
        "id": link.id,
        "album_id": link.album_id,
        "description": link.description,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "allow_download": link.allow_download,
        "show_exif": link.show_exif,
        "has_password": link.password_hash is not None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }
    # The raw key is returned exactly once, at creation time.
    if include_key is not None:
        data["key"] = include_key
        data["url"] = f"/api/public/shared/{include_key}"
    return data


# --- Management (owner) ----------------------------------------------------
@router.post("/shared-links")
def create_shared_link(
    request: SharedLinkCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    # The album must exist and be owned by the caller (IDOR guard).
    album_q = db.query(Album).filter(Album.id == request.album_id)
    if user is not None and user.role != "admin":
        album_q = album_q.filter(Album.owner_user_id == user.id)
    album = album_q.first()
    if not album:
        raise HTTPException(404, "Album not found")

    raw_key = secrets.token_urlsafe(32)
    link = SharedLink(
        key_hash=hash_token(raw_key),
        album_id=request.album_id,
        owner_user_id=user.id if user is not None else None,
        password_hash=hash_password(request.password) if request.password else None,
        description=request.description,
        expires_at=request.expires_at,
        allow_download=request.allow_download,
        show_exif=request.show_exif,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    # Raw key returned once; only its hash is stored.
    return _serialize_link(link, include_key=raw_key)


@router.get("/shared-links")
def list_shared_links(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    links = (
        _scope_links(db.query(SharedLink), user)
        .order_by(SharedLink.created_at.desc(), SharedLink.id.desc())
        .all()
    )
    return {
        "shared_links": [_serialize_link(link) for link in links],
        "total": len(links),
    }


@router.patch("/shared-links/{link_id}")
def update_shared_link(
    link_id: int,
    request: SharedLinkUpdate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    link = _load_owned_link_or_404(db, link_id, user)

    if request.description is not None:
        link.description = request.description
    if request.expires_at is not None:
        link.expires_at = request.expires_at
    if request.allow_download is not None:
        link.allow_download = request.allow_download
    if request.show_exif is not None:
        link.show_exif = request.show_exif
    if request.password is not None:
        # "" clears the password; non-empty sets a new bcrypt hash.
        link.password_hash = (
            hash_password(request.password) if request.password else None
        )

    db.commit()
    db.refresh(link)
    return _serialize_link(link)


@router.delete("/shared-links/{link_id}")
def delete_shared_link(
    link_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    link = _load_owned_link_or_404(db, link_id, user)
    db.delete(link)
    db.commit()
    return {"message": "Shared link revoked", "id": link_id}


# --- Public (capability URL) ----------------------------------------------
def _resolve_public_link(db: Session, key: str) -> SharedLink:
    """Look up a link by raw key (hashed), enforcing existence + expiry.

    Returns the link if valid; raises 404 for unknown/expired links (we use
    404 rather than 410/403 so the endpoint does not confirm a key ever
    existed).
    """
    link = db.query(SharedLink).filter(SharedLink.key_hash == hash_token(key)).first()
    if not link or _is_expired(link):
        raise HTTPException(404, "Shared link not found")
    return link


def _check_password(link: SharedLink, supplied: Optional[str]) -> None:
    """Enforce the link password (constant-time). 401 when required/incorrect."""
    if link.password_hash is None:
        return
    if not supplied or not verify_password_constant_time(supplied, link.password_hash):
        raise HTTPException(401, "Password required or incorrect")


def _serialize_public_item(media: Media, link: SharedLink, key: str) -> dict:
    """Public-safe item — NO raw storage keys, NO owner-scoped image URLs.

    All media bytes are served through share-scoped routes that re-validate the
    link on every request. The original URL is only offered when the link
    allows download.
    """
    item = {
        "id": media.id,
        "filename": media.filename,
        "width": media.width,
        "height": media.height,
        "created_at": media.created_at.isoformat() if media.created_at else None,
        "thumbnail_url": f"/api/public/shared/{key}/asset/{media.id}/thumbnail",
        "url": (
            f"/api/public/shared/{key}/asset/{media.id}/original"
            if link.allow_download
            else None
        ),
    }
    if link.show_exif and media.exif_json:
        item["exif"] = media.exif_json
    return item


def _shared_album_media_or_404(db: Session, link: SharedLink, media_id: int) -> Media:
    """Return a media row IFF it is a browsable member of the link's album.

    This is the single chokepoint that enforces share scoping at the byte
    layer: a media id outside the linked album, or archived/trashed/hidden,
    yields 404 — regardless of what id a viewer guesses.
    """
    media = (
        _browsable_media_query(db)
        .join(AlbumAsset, AlbumAsset.media_id == Media.id)
        .filter(AlbumAsset.album_id == link.album_id, Media.id == media_id)
        .first()
    )
    if not media:
        raise HTTPException(404, "Asset not found")
    return media


def _serve_object_bytes(
    object_key: Optional[str], content_type: Optional[str]
) -> Response:
    if not object_key:
        raise HTTPException(404, "Asset not found")
    try:
        data = get_file(object_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Shared-link asset fetch failed for %s: %s", object_key, exc)
        raise HTTPException(404, "Asset not found") from exc
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/public/shared/{key}")
def get_public_shared_link(
    key: str,
    password: Optional[str] = Query(None),
    x_share_password: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Return link metadata + the linked album's browsable assets.

    Access is scoped to exactly the linked album. Media bytes are served only
    through the share-scoped /asset routes below (never via raw storage keys
    or the owner-scoped image routes).
    """
    link = _resolve_public_link(db, key)
    _check_password(link, password or x_share_password)

    album = db.query(Album).filter(Album.id == link.album_id).first()
    if not album:
        # Album was deleted out from under the link.
        raise HTTPException(404, "Shared link not found")

    rows = (
        _browsable_media_query(db)
        .join(AlbumAsset, AlbumAsset.media_id == Media.id)
        .filter(AlbumAsset.album_id == link.album_id)
        .order_by(AlbumAsset.position.asc(), AlbumAsset.id.asc())
        .all()
    )

    items = [_serialize_public_item(media, link, key) for media in rows]

    return {
        "album": {"id": album.id, "name": album.name, "description": album.description},
        "allow_download": link.allow_download,
        "show_exif": link.show_exif,
        "items": items,
        "total": len(items),
    }


@router.get("/public/shared/{key}/asset/{media_id}/thumbnail")
def get_public_shared_thumbnail(
    key: str,
    media_id: int,
    password: Optional[str] = Query(None),
    x_share_password: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Serve a thumbnail for an asset in the link's album. Always permitted
    (thumbnails are low-res previews), but still scoped + password-gated."""
    link = _resolve_public_link(db, key)
    _check_password(link, password or x_share_password)
    media = _shared_album_media_or_404(db, link, media_id)
    if media.thumbnail_key:
        return _serve_object_bytes(media.thumbnail_key, media.thumbnail_content_type)
    # No generated thumbnail. Falling back to the original would hand out
    # full-resolution bytes through an ungated route — so only do so when the
    # link actually allows download; otherwise refuse (404).
    if not link.allow_download:
        raise HTTPException(404, "Thumbnail not available")
    return _serve_object_bytes(media.minio_key, media.content_type)


@router.get("/public/shared/{key}/asset/{media_id}/original")
def get_public_shared_original(
    key: str,
    media_id: int,
    password: Optional[str] = Query(None),
    x_share_password: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Serve the full-resolution original — ONLY when the link allows download."""
    link = _resolve_public_link(db, key)
    _check_password(link, password or x_share_password)
    if not link.allow_download:
        raise HTTPException(403, "Download is not permitted for this link")
    media = _shared_album_media_or_404(db, link, media_id)
    return _serve_object_bytes(media.minio_key, media.content_type)
