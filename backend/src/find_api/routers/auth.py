"""Authentication endpoints for small-team instance sharing.

Provides setup, login/logout, invite generation, join requests,
and admin approval workflows. All paths are relative to the /api
prefix added by main.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from find_api.core.auth import (
    create_session,
    generate_invite_token,
    hash_password,
    hash_token,
    is_shared_mode,
    verify_password,
)
from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_admin_user, get_required_user
from find_api.models.invite import InviteToken
from find_api.models.join_request import JoinRequest
from find_api.models.session import AuthSession
from find_api.models.user import User

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# --- Request / response schemas ---


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer when encoded as UTF-8")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class InviteCreateRequest(BaseModel):
    ttl_hours: Optional[int] = Field(None, gt=0, le=720)  # max 30 days


class JoinCreateRequest(BaseModel):
    invite_token: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: Optional[str] = Field(None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be 72 bytes or fewer when encoded as UTF-8")
        return v


def _user_dict(user: User) -> dict:
    """Serialize a User to a safe dict (no password hash)."""
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


def _ensure_admin_available(admin: Optional[User], db: Session) -> User:
    if admin is not None:
        return admin
    if not is_shared_mode(db):
        raise HTTPException(400, "Instance is not in shared mode")
    raise HTTPException(403, "Admin access required")


# --- Instance setup ---


@router.post("/auth/setup")
def setup_instance(
    body: SetupRequest,
    db: Session = Depends(get_db),
):
    """Create the admin account and activate shared mode.

    This endpoint only works once — on a fresh instance with no
    existing users. Calling it again returns 409.
    """
    if db.query(User).first() is not None:
        raise HTTPException(409, "Instance already set up")

    admin = User(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role="admin",
    )
    db.add(admin)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Instance already set up") from exc
    db.refresh(admin)

    raw_token, expires_at = create_session(db, admin.id)

    return {
        "user": _user_dict(admin),
        "token": raw_token,
        "expires_at": expires_at.isoformat(),
    }


# --- Login / logout ---


@router.post("/auth/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate with username and password.

    Returns a bearer token on success. Rate-limited to discourage
    brute-force attempts.
    """
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")

    if not user.is_active:
        raise HTTPException(403, "Account is deactivated")

    # Update last_login timestamp
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    raw_token, expires_at = create_session(db, user.id)

    return {
        "user": _user_dict(user),
        "token": raw_token,
        "expires_at": expires_at.isoformat(),
    }


@router.post("/auth/logout")
def logout(
    user: Optional[User] = Depends(get_required_user),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """End the current session."""
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[len("Bearer ") :]
        hashed = hash_token(raw_token)
        db.query(AuthSession).filter(AuthSession.token_hash == hashed).delete()
        db.commit()

    return {"message": "Logged out"}


@router.get("/auth/me")
def get_me(
    user: Optional[User] = Depends(get_required_user),
):
    """Return the currently authenticated user's info."""
    if user is None:
        # Local mode — no user concept
        return {"mode": "local", "user": None}

    return {"mode": "shared", "user": _user_dict(user)}


# --- Invite tokens ---


@router.post("/auth/invites")
def create_invite(
    body: Optional[InviteCreateRequest] = None,
    admin: Optional[User] = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Generate a single-use invite token.

    Admin only. The raw token is returned once and never stored.
    """
    admin = _ensure_admin_available(admin, db)
    body = body or InviteCreateRequest()

    ttl = body.ttl_hours or settings.INVITE_TTL_HOURS
    raw_token, token_hash = generate_invite_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)

    invite = InviteToken(
        token_hash=token_hash,
        created_by=admin.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return {
        "invite_token": raw_token,
        "expires_at": expires_at.isoformat(),
        "id": invite.id,
    }


@router.get("/auth/invites")
def list_invites(
    admin: Optional[User] = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List all invite tokens (metadata only, no raw tokens)."""
    _ensure_admin_available(admin, db)

    invites = db.query(InviteToken).order_by(InviteToken.created_at.desc()).all()
    return {
        "invites": [
            {
                "id": inv.id,
                "is_used": inv.is_used,
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invites
        ]
    }


# --- Join requests ---


@router.post("/auth/join")
def submit_join_request(
    body: JoinCreateRequest,
    db: Session = Depends(get_db),
):
    """Submit a join request using a valid invite token.

    The password is hashed immediately — plaintext is never stored.
    The invite token is marked as used (single-use).
    """
    if not is_shared_mode(db):
        raise HTTPException(400, "Instance is not in shared mode")

    # Validate invite token
    token_hash = hash_token(body.invite_token)
    invite = (
        db.query(InviteToken)
        .filter(
            InviteToken.token_hash == token_hash,
            InviteToken.is_used.is_(False),
        )
        .first()
    )
    if invite is None:
        raise HTTPException(400, "Invalid or already used invite token")

    now = datetime.now(timezone.utc)
    if invite.expires_at:
        expiry = invite.expires_at
        # Ensure timezone-aware comparison
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < now:
            raise HTTPException(400, "Invite token has expired")

    # Check username availability against existing users and pending requests
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "Username is already taken")
    if (
        db.query(JoinRequest)
        .filter(
            JoinRequest.username == body.username,
            JoinRequest.status == "pending",
        )
        .first()
    ):
        raise HTTPException(
            409, "A pending join request with this username already exists"
        )

    # Mark invite as used
    invite.is_used = True

    join_req = JoinRequest(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        invite_token_id=invite.id,
    )
    db.add(join_req)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username is already taken")
    db.refresh(join_req)

    return {
        "join_request_id": join_req.id,
        "status": join_req.status,
    }


@router.get("/auth/join-requests")
def list_join_requests(
    admin: Optional[User] = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """List all join requests. Admin only."""
    _ensure_admin_available(admin, db)

    requests = db.query(JoinRequest).order_by(JoinRequest.created_at.desc()).all()
    return {
        "requests": [
            {
                "id": req.id,
                "username": req.username,
                "display_name": req.display_name,
                "status": req.status,
                "created_at": req.created_at.isoformat() if req.created_at else None,
                "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
            }
            for req in requests
        ]
    }


@router.post("/auth/join-requests/{request_id}/approve")
def approve_join_request(
    request_id: int,
    admin: Optional[User] = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Approve a pending join request and create the user account."""
    admin = _ensure_admin_available(admin, db)

    join_req = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if join_req is None:
        raise HTTPException(404, "Join request not found")
    if join_req.status != "pending":
        raise HTTPException(400, f"Join request is already {join_req.status}")

    # Double-check username isn't taken (race condition guard)
    if db.query(User).filter(User.username == join_req.username).first():
        raise HTTPException(409, "Username was taken since the request was submitted")

    new_user = User(
        username=join_req.username,
        display_name=join_req.display_name,
        password_hash=join_req.password_hash,
        role="member",
    )
    db.add(new_user)

    join_req.status = "approved"
    join_req.reviewed_by = admin.id
    join_req.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(new_user)

    return {"user": _user_dict(new_user)}


@router.post("/auth/join-requests/{request_id}/reject")
def reject_join_request(
    request_id: int,
    admin: Optional[User] = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Reject a pending join request."""
    admin = _ensure_admin_available(admin, db)

    join_req = db.query(JoinRequest).filter(JoinRequest.id == request_id).first()
    if join_req is None:
        raise HTTPException(404, "Join request not found")
    if join_req.status != "pending":
        raise HTTPException(400, f"Join request is already {join_req.status}")

    join_req.status = "rejected"
    join_req.reviewed_by = admin.id
    join_req.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Join request rejected"}
