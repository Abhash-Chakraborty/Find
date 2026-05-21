"""Vault endpoints for unlocking, hiding, and streaming encrypted images."""

from __future__ import annotations

import os
import secrets
import tempfile
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
    delete_session_key,
    decrypt_file_stream,
    derive_master_key,
    get_session_key,
    encrypt_file,
    set_session_key,
)
from find_api.core.database import get_db
from find_api.core.storage import get_file, delete_file
from find_api.models.media import Media

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class VaultUnlockRequest(BaseModel):
    passphrase: str


class VaultLockRequest(BaseModel):
    session_token: Optional[str] = None


class VaultHideRequest(BaseModel):
    media_id: int
    session_token: Optional[str] = None


def _normalize_binary(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


def _resolve_session_token(
    authorization: Optional[str], session_token: Optional[str]
) -> str:
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
    try:
        return get_session_key(session_token)
    except KeyError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid or expired vault session"
        ) from exc


def _load_or_create_vault_salt(db: Session) -> bytes:
    row = db.execute(text("SELECT salt FROM vault_config ORDER BY id ASC LIMIT 1")).first()
    if row and row[0] is not None:
        return _normalize_binary(row[0])

    salt = os.urandom(16)
    try:
        dialect_name = db.get_bind().dialect.name
    except Exception:
        dialect_name = "postgresql"
    if dialect_name == "sqlite":
        db.execute(
            text("INSERT OR IGNORE INTO vault_config (id, salt) VALUES (1, :salt)"),
            {"salt": salt},
        )
    else:
        db.execute(
            text(
                "INSERT INTO vault_config (id, salt) VALUES (1, :salt) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"salt": salt},
        )
    db.commit()

    row = db.execute(text("SELECT salt FROM vault_config ORDER BY id ASC LIMIT 1")).first()
    if not row or row[0] is None:
        raise HTTPException(status_code=500, detail="Failed to initialize vault salt")
    return _normalize_binary(row[0])


def _load_media_or_404(db: Session, media_id: int) -> Media:
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Image not found")
    return media


def _load_vault_metadata(db: Session, media_id: int) -> Optional[tuple[str, bytes]]:
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


@router.post("/vault/unlock")
@limiter.limit("5/minute")
def unlock_vault(
    request: Request,
    payload: VaultUnlockRequest,
    db: Session = Depends(get_db),
):
    if not payload.passphrase or not payload.passphrase.strip():
        raise HTTPException(
            status_code=400, detail="Passphrase must not be empty"
        )
    salt = _load_or_create_vault_salt(db)
    master_key = derive_master_key(payload.passphrase, salt)
    session_token = secrets.token_urlsafe(32)
    set_session_key(session_token, master_key)
    return {"session_token": session_token}


@router.get("/vault/list")
def list_vault_media(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
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
    session_token = _resolve_session_token(authorization, payload.session_token)
    master_key = _get_cached_master_key(session_token)

    media = _load_media_or_404(db, payload.media_id)
    if media.is_hidden:
        raise HTTPException(status_code=409, detail="Image is already hidden")

    existing_metadata = _load_vault_metadata(db, media.id)
    if existing_metadata is not None:
        raise HTTPException(status_code=409, detail="Vault metadata already exists")

    source_bytes = get_file(media.minio_key)
    encrypted_path = VAULT_STORAGE_DIR / f"{media.id}-{uuid4().hex}.enc"
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_source_path = tempfile.mkstemp(prefix=f"vault-source-{media.id}-")
    os.close(fd)

    try:
        with open(temp_source_path, "wb") as temp_handle:
            temp_handle.write(source_bytes)

        iv = encrypt_file(master_key, temp_source_path, str(encrypted_path))

        db.execute(
            text(
                "INSERT INTO vault_metadata (media_id, encrypted_path, iv) "
                "VALUES (:media_id, :encrypted_path, :iv)"
            ),
            {
                "media_id": media.id,
                "encrypted_path": str(encrypted_path),
                "iv": iv,
            },
        )
        media.is_hidden = True
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        Path(encrypted_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to hide image") from exc
    else:
        delete_file(media.minio_key)
    finally:
        Path(temp_source_path).unlink(missing_ok=True)

    return {"status": "hidden", "media_id": media.id}


@router.get("/vault/stream/{media_id}")
def stream_hidden_media(
    media_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
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

    return StreamingResponse(
        decrypt_file_stream(master_key, iv, str(encrypted_file)),
        media_type=media.content_type or "application/octet-stream",
    )
