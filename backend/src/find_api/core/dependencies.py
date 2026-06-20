"""FastAPI dependencies for authentication.

These are injected into route handlers via Depends(). In local mode
(no admin user exists) they are permissive — existing single-user
behavior is completely unchanged.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from find_api.core.auth import get_current_user, is_shared_mode
from find_api.core.database import get_db
from find_api.models.user import User


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
