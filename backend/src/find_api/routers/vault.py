"""Vault endpoints for unlocking, hiding, and streaming encrypted images."""

from __future__ import annotations

import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from find_api.core.crypto import (
    VAULT_STORAGE_DIR,
    build_vault_aad,
    create_key_verifier,
    delete_session_key,
    decrypt_file_stream,
    derive_master_key,
    verify_master_key,
    get_session_key,
    encrypt_file,
    set_session_key,
)
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.core.storage import delete_file, download_file_to_path
from find_api.models.media import Media
from find_api.models.user import User

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
ENCRYPTION_ALGORITHM = "AES-256-GCM"
KEY_DERIVATION_METHOD = "PBKDF2-HMAC-SHA256"

# Minimum passphrase length enforced when a vault is first created. Existing
# vaults are not re-validated on unlock so short legacy passphrases keep working.
MIN_VAULT_PASSPHRASE_LENGTH = 8


class VaultUnlockRequest(BaseModel):
    passphrase: str


class VaultLockRequest(BaseModel):
    session_token: Optional[str] = None


class VaultHideRequest(BaseModel):
    media_id: int
    session_token: Optional[str] = None


def _normalize_binary(value: object) -> bytes:
    """Convert database BLOB-like values to plain bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


def _resolve_session_token(
    authorization: Optional[str], session_token: Optional[str]
) -> str:
    """Resolve a vault session token from the request body or Authorization header."""
    token = session_token.strip() if session_token else ""

    if not token and authorization:
        scheme, _, raw_token = authorization.partition(" ")
        if scheme.lower() == "bearer" and raw_token:
            token = raw_token.strip()
        else:
            token = authorization.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing vault session token")

    return token


def _get_cached_master_key(session_token: str) -> bytes:
    """Load the cached vault master key or translate cache misses to HTTP errors."""
    try:
        return get_session_key(session_token)
    except KeyError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid or expired vault session"
        ) from exc


def _load_vault_config(db: Session) -> Optional[tuple[bytes, bytes, bytes]]:
    """Return the singleton vault verifier configuration when it exists."""
    row = db.execute(
        text(
            "SELECT salt, verifier_nonce, verifier_ciphertext "
            "FROM vault_config ORDER BY id ASC LIMIT 1"
        )
    ).first()
    if not row:
        return None
    if row[0] is None or row[1] is None or row[2] is None:
        return None
    return (
        _normalize_binary(row[0]),
        _normalize_binary(row[1]),
        _normalize_binary(row[2]),
    )


def _create_vault_config(db: Session, passphrase: str) -> bytes:
    """Initialize vault verifier state and return the derived master key."""
    salt = os.urandom(16)
    master_key = derive_master_key(passphrase, salt)
    verifier_nonce, verifier_ciphertext = create_key_verifier(master_key)

    try:
        dialect_name = db.get_bind().dialect.name
    except Exception:
        dialect_name = "postgresql"
    if dialect_name == "sqlite":
        db.execute(
            text(
                "INSERT OR IGNORE INTO vault_config "
                "(id, salt, verifier_nonce, verifier_ciphertext) "
                "VALUES (1, :salt, :verifier_nonce, :verifier_ciphertext)"
            ),
            {
                "salt": salt,
                "verifier_nonce": verifier_nonce,
                "verifier_ciphertext": verifier_ciphertext,
            },
        )
    else:
        db.execute(
            text(
                "INSERT INTO vault_config "
                "(id, salt, verifier_nonce, verifier_ciphertext) "
                "VALUES (1, :salt, :verifier_nonce, :verifier_ciphertext) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "salt": salt,
                "verifier_nonce": verifier_nonce,
                "verifier_ciphertext": verifier_ciphertext,
            },
        )
    db.commit()

    config = _load_vault_config(db)
    if config is None:
        raise HTTPException(status_code=500, detail="Failed to initialize vault")

    stored_salt, stored_nonce, stored_ciphertext = config
    stored_key = derive_master_key(passphrase, stored_salt)
    if not verify_master_key(stored_key, stored_nonce, stored_ciphertext):
        raise HTTPException(status_code=401, detail="Invalid vault passphrase")
    return stored_key


def _load_or_create_master_key(db: Session, passphrase: str) -> bytes:
    """Load an existing vault key or initialize vault config on first unlock."""
    config = _load_vault_config(db)
    if config is None:
        return _create_vault_config(db, passphrase)

    salt, verifier_nonce, verifier_ciphertext = config
    master_key = derive_master_key(passphrase, salt)
    if not verify_master_key(master_key, verifier_nonce, verifier_ciphertext):
        raise HTTPException(status_code=401, detail="Invalid vault passphrase")
    return master_key


def _load_media_or_404(db: Session, media_id: int) -> Media:
    """Return a media row or raise the public image-not-found response."""
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Image not found")
    return media


def _load_vault_metadata(db: Session, media_id: int) -> Optional[tuple[str, bytes]]:
    """Return encrypted vault blob metadata for a media row."""
    row = db.execute(
        text(
            "SELECT encrypted_path, iv "
            "FROM vault_metadata "
            "WHERE media_id = :media_id"
        ),
        {"media_id": media_id},
    ).first()
    if not row:
        return None
    return row[0], _normalize_binary(row[1])


def _rollback_hidden_state_after_delete_failure(
    db: Session, media: Media, encrypted_path: Path
) -> None:
    """Best-effort rollback when original object deletion fails after encryption."""
    try:
        db.execute(
            text("DELETE FROM vault_metadata WHERE media_id = :media_id"),
            {"media_id": media.id},
        )
        media.is_hidden = False
        media.vault_state = "visible"
        media.hidden_at = None
        media.encrypted_at = None
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        encrypted_path.unlink(missing_ok=True)


@router.post("/vault/unlock")
@limiter.limit("5/minute")
def unlock_vault(
    request: Request,
    payload: VaultUnlockRequest,
    db: Session = Depends(get_db),
    _user: Optional[User] = Depends(get_required_user),
):
    """Unlock the vault and cache a short-lived session token."""
    if not payload.passphrase or not payload.passphrase.strip():
        raise HTTPException(status_code=400, detail="Passphrase must not be empty")

    # When no vault exists yet, the first unlock *creates* it with this
    # passphrase. Enforce a minimum length at creation time so the global
    # vault secret cannot be a trivial passphrase. Existing vaults are not
    # re-validated, so previously-set passphrases keep working.
    if _load_vault_config(db) is None:
        if len(payload.passphrase) < MIN_VAULT_PASSPHRASE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Vault passphrase must be at least "
                    f"{MIN_VAULT_PASSPHRASE_LENGTH} characters"
                ),
            )

    master_key = _load_or_create_master_key(db, payload.passphrase)
    session_token = secrets.token_urlsafe(32)
    set_session_key(session_token, master_key)
    return {"session_token": session_token}


@router.get("/vault/list")
def list_vault_media(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """List media records hidden in the vault for an unlocked session."""
    token = _resolve_session_token(authorization, None)
    _get_cached_master_key(token)

    media_items = (
        db.query(Media)
        .filter(Media.is_hidden.is_(True))
        .order_by(Media.created_at.desc())
        .all()
    )

    return [
        {
            "id": media.id,
            "filename": media.filename,
            "content_type": media.content_type,
            "created_at": media.created_at.isoformat() if media.created_at else None,
        }
        for media in media_items
    ]


@router.post("/vault/lock")
def lock_vault(
    payload: Optional[VaultLockRequest] = Body(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Invalidate an active vault session token."""
    session_token = _resolve_session_token(
        authorization, payload.session_token if payload else None
    )
    if not delete_session_key(session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired vault session")
    return {"status": "locked"}


@router.post("/vault/hide")
def hide_media(
    payload: VaultHideRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Encrypt a media object into the vault and remove the original blob."""
    session_token = _resolve_session_token(authorization, payload.session_token)
    master_key = _get_cached_master_key(session_token)

    media = _load_media_or_404(db, payload.media_id)
    if media.is_hidden:
        raise HTTPException(status_code=409, detail="Image is already hidden")

    existing_metadata = _load_vault_metadata(db, media.id)
    if existing_metadata is not None:
        raise HTTPException(status_code=409, detail="Vault metadata already exists")

    encrypted_path = VAULT_STORAGE_DIR / f"{media.id}-{uuid4().hex}.enc"
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_source_path = tempfile.mkstemp(prefix=f"vault-source-{media.id}-")
    os.close(fd)

    try:
        try:
            download_file_to_path(media.minio_key, temp_source_path)
            aad = build_vault_aad(media.id, media.file_hash)
            iv = encrypt_file(
                master_key,
                temp_source_path,
                str(encrypted_path),
                associated_data=aad,
            )

            db.execute(
                text(
                    "INSERT INTO vault_metadata "
                    "(media_id, encrypted_path, iv, encryption_algorithm, key_derivation, ciphertext_size) "
                    "VALUES (:media_id, :encrypted_path, :iv, :encryption_algorithm, :key_derivation, :ciphertext_size)"
                ),
                {
                    "media_id": media.id,
                    "encrypted_path": str(encrypted_path),
                    "iv": iv,
                    "encryption_algorithm": ENCRYPTION_ALGORITHM,
                    "key_derivation": KEY_DERIVATION_METHOD,
                    "ciphertext_size": encrypted_path.stat().st_size,
                },
            )
            media.is_hidden = True
            media.vault_state = "hidden_encrypted"
            hidden_timestamp = datetime.now(timezone.utc)
            media.hidden_at = hidden_timestamp
            media.encrypted_at = hidden_timestamp
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            encrypted_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Failed to hide image") from exc

        try:
            delete_file(media.minio_key)
        except Exception as exc:  # noqa: BLE001
            _rollback_hidden_state_after_delete_failure(db, media, encrypted_path)
            raise HTTPException(
                status_code=500,
                detail="Failed to remove original image from storage",
            ) from exc
    finally:
        Path(temp_source_path).unlink(missing_ok=True)

    return {"status": "hidden", "media_id": media.id}


@router.get("/vault/stream/{media_id}")
def stream_hidden_media(
    media_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Stream a hidden media blob after AEAD metadata verification succeeds."""
    token = _resolve_session_token(authorization, None)
    master_key = _get_cached_master_key(token)
    media = _load_media_or_404(db, media_id)
    if not media.is_hidden:
        raise HTTPException(status_code=404, detail="Image not found")
    metadata = _load_vault_metadata(db, media_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Vault metadata not found")

    encrypted_path, iv = metadata
    encrypted_file = Path(encrypted_path)
    if not encrypted_file.exists():
        raise HTTPException(status_code=404, detail="Encrypted vault blob not found")

    aad = build_vault_aad(media.id, media.file_hash)
    return StreamingResponse(
        decrypt_file_stream(
            master_key,
            iv,
            str(encrypted_file),
            associated_data=aad,
        ),
        media_type=media.content_type or "application/octet-stream",
    )
