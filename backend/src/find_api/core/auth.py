"""Authentication helpers for small-team instance sharing.

Handles password hashing (bcrypt), session token generation,
invite token generation, and shared-mode detection.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.models.session import AuthSession
from find_api.models.user import User


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against its bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_token(raw: str) -> str:
    """Return the SHA-256 hex digest of a raw token string.

    Tokens stored in the database are always hashed so a DB leak
    does not expose usable session or invite tokens.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_session_token() -> tuple[str, str]:
    """Create a new session token.

    Returns:
        (raw_token, token_hash) — send raw_token to the client,
        store token_hash in the database.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def generate_invite_token() -> tuple[str, str]:
    """Create a new invite token (256-bit entropy).

    Returns:
        (raw_token, token_hash) — give raw_token to the admin,
        store token_hash in the database.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def is_shared_mode(db: Session) -> bool:
    """Return True when the instance is running in shared mode.

    Shared mode is active when at least one admin user exists.
    A fresh install with no users is local (single-user) mode.
    """
    return db.query(User).filter(User.role == "admin").first() is not None


def get_current_user(
    db: Session,
    authorization: Optional[str],
) -> Optional[User]:
    """Resolve the authenticated user from a bearer token.

    Returns None when the token is missing or invalid. Does NOT
    enforce authentication — callers decide whether to 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    raw_token = authorization[len("Bearer ") :]
    hashed = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == hashed,
            AuthSession.expires_at > now,
        )
        .first()
    )
    if session is None:
        return None

    user = (
        db.query(User)
        .filter(User.id == session.user_id, User.is_active.is_(True))
        .first()
    )
    return user


def create_session(db: Session, user_id: int) -> tuple[str, datetime]:
    """Insert a new session row and return (raw_token, expires_at)."""
    raw_token, token_hash = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.SESSION_TTL_HOURS
    )

    session_row = AuthSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(session_row)
    db.commit()

    return raw_token, expires_at
