"""Partner sharing — directed user-to-user read access.

A partner grant lets the sharer's browsable media be *read* by the partner,
without widening the global media scoping (see models/partner_share.py for the
rationale). All endpoints require a real authenticated user; partner sharing is
meaningless in local (single-user) mode and is rejected there.

Security model:
- Create/revoke act on grants the current user *owns as the sharer* (IDOR
  guard: you can only grant/revoke access to your own library).
- The read endpoint is gated on an existing grant (sharer -> me). Without one
  it returns 404 — never confirming whether the sharer or their media exists.
- Read-only: a partner can browse but never mutate the sharer's media.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.core.storage import get_file
from find_api.models.media import Media
from find_api.models.partner_share import PartnerShare
from find_api.models.user import User
from find_api.routers.gallery import _browsable_media_query

logger = logging.getLogger(__name__)

router = APIRouter()


class PartnerShareCreate(BaseModel):
    partner_user_id: int


def _require_shared_mode_user(user: Optional[User]) -> User:
    """Partner sharing needs a real user. Local mode (user is None) → 400."""
    if user is None:
        raise HTTPException(
            400, "Partner sharing is only available in shared (multi-user) mode."
        )
    return user


def _serialize_partner_item(media: Media, sharer_user_id: int) -> dict:
    """Partner-safe item — NO raw storage keys, NO owner-scoped image URLs.

    Mirrors the public shared-link serializer: bytes are served only through
    the grant-checked partner byte routes below (which re-validate the grant on
    every request), so revoking a grant immediately cuts off access and storage
    keys never leave the server.
    """
    return {
        "id": media.id,
        "filename": media.filename,
        "status": media.status,
        "width": media.width,
        "height": media.height,
        "file_size": media.file_size,
        "created_at": media.created_at.isoformat() if media.created_at else None,
        "thumbnail_url": (f"/api/partners/{sharer_user_id}/media/{media.id}/thumbnail"),
        "url": f"/api/partners/{sharer_user_id}/media/{media.id}/original",
    }


def _serve_object_bytes(
    object_key: Optional[str], content_type: Optional[str]
) -> Response:
    if not object_key:
        raise HTTPException(404, "Asset not found")
    try:
        data = get_file(object_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Partner asset fetch failed for %s: %s", object_key, exc)
        raise HTTPException(404, "Asset not found") from exc
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


def _serialize_share(share: PartnerShare, db: Session) -> dict:
    sharer = db.query(User).filter(User.id == share.sharer_user_id).first()
    partner = db.query(User).filter(User.id == share.partner_user_id).first()
    return {
        "id": share.id,
        "sharer_user_id": share.sharer_user_id,
        "partner_user_id": share.partner_user_id,
        "sharer_username": sharer.username if sharer else None,
        "partner_username": partner.username if partner else None,
        "created_at": share.created_at.isoformat() if share.created_at else None,
    }


@router.post("/partners")
def create_partner_share(
    request: PartnerShareCreate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Grant a partner read access to the current user's library."""
    me = _require_shared_mode_user(user)

    if request.partner_user_id == me.id:
        raise HTTPException(400, "You cannot share with yourself.")

    partner = (
        db.query(User)
        .filter(User.id == request.partner_user_id, User.is_active.is_(True))
        .first()
    )
    if not partner:
        raise HTTPException(404, "Partner user not found")

    existing = (
        db.query(PartnerShare)
        .filter(
            PartnerShare.sharer_user_id == me.id,
            PartnerShare.partner_user_id == request.partner_user_id,
        )
        .first()
    )
    if existing:
        return _serialize_share(existing, db)

    share = PartnerShare(sharer_user_id=me.id, partner_user_id=request.partner_user_id)
    db.add(share)
    db.commit()
    db.refresh(share)
    return _serialize_share(share, db)


@router.get("/partners")
def list_partner_shares(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """List grants the current user created (outgoing) and received (incoming)."""
    me = _require_shared_mode_user(user)

    outgoing = (
        db.query(PartnerShare)
        .filter(PartnerShare.sharer_user_id == me.id)
        .order_by(PartnerShare.created_at.desc(), PartnerShare.id.desc())
        .all()
    )
    incoming = (
        db.query(PartnerShare)
        .filter(PartnerShare.partner_user_id == me.id)
        .order_by(PartnerShare.created_at.desc(), PartnerShare.id.desc())
        .all()
    )
    return {
        "shared_with": [_serialize_share(s, db) for s in outgoing],
        "shared_with_me": [_serialize_share(s, db) for s in incoming],
    }


@router.delete("/partners/{share_id}")
def revoke_partner_share(
    share_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Revoke a grant. Only the sharer who created it may revoke it (IDOR guard)."""
    me = _require_shared_mode_user(user)

    share = (
        db.query(PartnerShare)
        .filter(
            PartnerShare.id == share_id,
            PartnerShare.sharer_user_id == me.id,
        )
        .first()
    )
    if not share:
        raise HTTPException(404, "Partner share not found")

    db.delete(share)
    db.commit()
    return {"message": "Partner share revoked", "id": share_id}


def _require_grant_or_404(db: Session, sharer_user_id: int, me: User) -> None:
    """Raise 404 unless an active grant (sharer -> me) exists.

    The single chokepoint for partner access: used by both the listing and the
    byte routes so revoking a grant immediately cuts off everything.
    """
    grant = (
        db.query(PartnerShare)
        .filter(
            PartnerShare.sharer_user_id == sharer_user_id,
            PartnerShare.partner_user_id == me.id,
        )
        .first()
    )
    if not grant:
        # Do not confirm whether the sharer exists or simply hasn't shared.
        raise HTTPException(404, "No shared library found")


def _partner_media_or_404(db: Session, sharer_user_id: int, media_id: int) -> Media:
    """Return a media row IFF it is browsable and owned by the sharer.

    Mirrors the shared-link byte chokepoint: a media id outside the sharer's
    browsable library yields 404 regardless of what id the partner guesses.
    """
    media = (
        _browsable_media_query(db)
        .filter(Media.id == media_id, Media.uploader_user_id == sharer_user_id)
        .first()
    )
    if not media:
        raise HTTPException(404, "Asset not found")
    return media


@router.get("/partners/{sharer_user_id}/media")
def list_partner_media(
    sharer_user_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """List a sharer's browsable media — only if they shared with me.

    The grant is the gate: without ``(sharer -> me)`` this 404s, so a partner
    cannot read an arbitrary user's library by guessing ids. Media is filtered
    explicitly to the sharer (NOT via scope_media_query, which would scope to
    *my* media) and to the browsable set, so archived/trashed/hidden never leak.
    Items expose only grant-checked byte-route URLs — never raw storage keys.
    """
    me = _require_shared_mode_user(user)
    _require_grant_or_404(db, sharer_user_id, me)

    rows = (
        _browsable_media_query(db)
        .filter(Media.uploader_user_id == sharer_user_id)
        .order_by(Media.created_at.desc(), Media.id.desc())
        .all()
    )
    return {
        "sharer_user_id": sharer_user_id,
        "items": [_serialize_partner_item(m, sharer_user_id) for m in rows],
        "total": len(rows),
    }


@router.get("/partners/{sharer_user_id}/media/{media_id}/thumbnail")
def get_partner_thumbnail(
    sharer_user_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Serve a thumbnail for a shared asset — re-validates the grant per request."""
    me = _require_shared_mode_user(user)
    _require_grant_or_404(db, sharer_user_id, me)
    media = _partner_media_or_404(db, sharer_user_id, media_id)
    if media.thumbnail_key:
        return _serve_object_bytes(media.thumbnail_key, media.thumbnail_content_type)
    # No generated thumbnail — fall back to the original (partner reads are
    # allowed to see full-res; there is no download gate for partner sharing).
    return _serve_object_bytes(media.minio_key, media.content_type)


@router.get("/partners/{sharer_user_id}/media/{media_id}/original")
def get_partner_original(
    sharer_user_id: int,
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Serve the full-resolution original — re-validates the grant per request."""
    me = _require_shared_mode_user(user)
    _require_grant_or_404(db, sharer_user_id, me)
    media = _partner_media_or_404(db, sharer_user_id, media_id)
    return _serve_object_bytes(media.minio_key, media.content_type)
