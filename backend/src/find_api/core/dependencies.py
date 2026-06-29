"""FastAPI dependencies for authentication.

These are injected into route handlers via Depends(). In local mode
(no admin user exists) they are permissive — existing single-user
behavior is completely unchanged.
"""

from __future__ import annotations

from typing import Optional, TypeVar

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Query, Session

from find_api.core.auth import get_current_user, is_shared_mode
from find_api.core.database import get_db
from find_api.models.media import Media
from find_api.models.user import User

Q = TypeVar("Q", bound=Query)


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user if present, None otherwise.

    Never raises — use this for endpoints that work in both local
    and shared mode (e.g. upload records the uploader when known).
    """
    return get_current_user(db, authorization)


def get_required_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user or raise 401 in shared mode.

    In local mode (no admin exists) this returns None silently,
    preserving the existing unauthenticated behavior.
    """
    user = get_current_user(db, authorization)
    if user is not None:
        return user

    if is_shared_mode(db):
        raise HTTPException(status_code=401, detail="Authentication required")

    # Local mode — no auth needed
    return None


def get_admin_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user only if they have admin role.

    Raises 401 if not authenticated (in shared mode).
    Raises 403 if authenticated but not an admin.
    In local mode, returns None.
    """
    user = get_required_user(authorization=authorization, db=db)
    if user is None:
        return None  # local mode

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


def scope_media_query(query: Q, user: Optional[User]) -> Q:
    """Restrict a Media query to rows the user is allowed to see.

    - Local mode (user is None): no restriction — single-user behavior.
    - Admin user: no restriction — admins see every uploader's media.
    - Regular user: only rows they uploaded (uploader_user_id == user.id).

    Used so shared-mode endpoints cannot enumerate or mutate other
    users' media by guessing integer ids (IDOR).
    """
    if user is None or user.role == "admin":
        return query
    return query.filter(Media.uploader_user_id == user.id)


def can_access_media(media: Media, user: Optional[User]) -> bool:
    """Return True when the user may read/mutate this specific media row.

    Mirrors :func:`scope_media_query` for single-object lookups. In local
    mode or for admins this is always True; otherwise the caller must own
    the row. Callers should return 404 (not 403) on False to avoid
    leaking the existence of other users' media.
    """
    if user is None or user.role == "admin":
        return True
    return media.uploader_user_id == user.id
