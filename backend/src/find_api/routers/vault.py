"""Vault endpoints for unlocking, hiding, and streaming encrypted images."""

from __future__ import annotations

import os
import logging
import secrets
import tempfile
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from PIL import Image, ImageOps, UnidentifiedImageError
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
    encrypt_file,
    get_session_key,
    set_session_key,
    verify_master_key,
)
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.core.storage import (
    delete_file,
    download_file_to_path,
    upload_file,
    upload_thumbnail,
)
from find_api.models.media import Media
from find_api.models.user import User

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)
ENCRYPTION_ALGORITHM = "AES-256-GCM"
KEY_DERIVATION_METHOD = "Argon2id"
VAULT_THUMBNAIL_MAX_SIZE = (320, 320)
VAULT_THUMBNAIL_CONTENT_TYPE = "image/webp"

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


class VaultRestoreRequest(BaseModel):
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
            "SELECT encrypted_path, iv FROM vault_metadata WHERE media_id = :media_id"
        ),
        {"media_id": media_id},
    ).first()
    if not row:
        return None
    return row[0], _normalize_binary(row[1])


def _apply_thumbnail_metadata(media: Media, metadata: Optional[dict]) -> None:
    """Apply generated thumbnail metadata or clear stale thumbnail pointers."""
    media.thumbnail_key = metadata.get("thumbnail_key") if metadata else None
    media.thumbnail_content_type = (
        metadata.get("thumbnail_content_type") if metadata else None
    )
    media.thumbnail_size = metadata.get("thumbnail_size") if metadata else None
    media.thumbnail_width = metadata.get("thumbnail_width") if metadata else None
    media.thumbnail_height = metadata.get("thumbnail_height") if metadata else None


def _delete_storage_objects_best_effort(*object_keys: Optional[str]) -> None:
    """Remove rollback artifacts without masking the primary failure."""
    for object_key in dict.fromkeys(key for key in object_keys if key):
        try:
            delete_file(object_key)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to remove vault rollback object %s", object_key)


def _rollback_hidden_state_after_delete_failure(
    db: Session,
    media: Media,
    encrypted_path: Path,
    plaintext_path: Path,
    *,
    original_key: str,
    content_type: str,
    file_hash: str,
    had_thumbnail: bool,
) -> bool:
    """Restore plaintext storage before making a failed hide visible again.

    The encrypted blob and hidden database state remain authoritative until the
    original object has been replaced successfully. This prevents a storage
    deletion failure from leaving a visible row whose object no longer exists.
    """
    uploaded_thumbnail: Optional[dict] = None
    try:
        plaintext = plaintext_path.read_bytes()
        upload_file(plaintext, original_key, content_type)
        if had_thumbnail:
            uploaded_thumbnail = upload_thumbnail(plaintext, file_hash)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to restore plaintext while rolling back vault hide")
        return False

    try:
        db.execute(
            text("DELETE FROM vault_metadata WHERE media_id = :media_id"),
            {"media_id": media.id},
        )
        media.is_hidden = False
        media.vault_state = "visible"
        media.hidden_at = None
        media.encrypted_at = None
        if had_thumbnail:
            _apply_thumbnail_metadata(media, uploaded_thumbnail)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        _delete_storage_objects_best_effort(
            original_key,
            uploaded_thumbnail.get("thumbnail_key") if uploaded_thumbnail else None,
        )
        return False

    encrypted_path.unlink(missing_ok=True)
    return True


def _decrypt_to_temporary_path(
    master_key: bytes,
    iv: bytes,
    encrypted_file: Path,
    *,
    associated_data: bytes,
    prefix: str,
) -> Path:
    """Decrypt and authenticate a vault blob into a short-lived local file."""
    fd, plaintext_path = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    plaintext_file = Path(plaintext_path)

    try:
        with plaintext_file.open("wb") as output:
            for chunk in decrypt_file_stream(
                master_key,
                iv,
                str(encrypted_file),
                associated_data=associated_data,
            ):
                output.write(chunk)
    except Exception:
        plaintext_file.unlink(missing_ok=True)
        raise

    return plaintext_file


def _render_vault_thumbnail(plaintext_file: Path) -> bytes:
    """Render a bounded WEBP preview without returning the decrypted original."""
    with Image.open(plaintext_file) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.thumbnail(VAULT_THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(output, format="WEBP", quality=76, method=4)
        return output.getvalue()


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
            "width": media.width,
            "height": media.height,
            "created_at": media.created_at.isoformat() if media.created_at else None,
            "hidden_at": media.hidden_at.isoformat() if media.hidden_at else None,
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

    original_key = media.minio_key
    thumbnail_key = media.thumbnail_key
    content_type = media.content_type or "application/octet-stream"
    file_hash = media.file_hash
    encrypted_path = VAULT_STORAGE_DIR / f"{media.id}-{uuid4().hex}.enc"
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_source_path = tempfile.mkstemp(prefix=f"vault-source-{media.id}-")
    os.close(fd)

    try:
        try:
            download_file_to_path(original_key, temp_source_path)
            aad = build_vault_aad(media.id, file_hash)
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
            delete_file(original_key)
            if thumbnail_key:
                delete_file(thumbnail_key)
        except Exception as exc:  # noqa: BLE001
            rolled_back = _rollback_hidden_state_after_delete_failure(
                db,
                media,
                encrypted_path,
                Path(temp_source_path),
                original_key=original_key,
                content_type=content_type,
                file_hash=file_hash,
                had_thumbnail=thumbnail_key is not None,
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to remove plaintext image from storage"
                    if rolled_back
                    else "Failed to remove plaintext image safely; encrypted copy retained"
                ),
            ) from exc
    finally:
        Path(temp_source_path).unlink(missing_ok=True)

    return {"status": "hidden", "media_id": media.id}


@router.post("/vault/restore")
def restore_media(
    payload: VaultRestoreRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Restore an authenticated vault item to configured storage safely.

    The encrypted blob remains the rollback source until storage replacement
    and the visible-state database transaction both succeed. It is staged by an
    atomic local rename while the database transition commits, then deleted.
    """
    session_token = _resolve_session_token(authorization, payload.session_token)
    master_key = _get_cached_master_key(session_token)

    media = _load_media_or_404(db, payload.media_id)
    if not media.is_hidden:
        raise HTTPException(status_code=409, detail="Image is not hidden")

    metadata = _load_vault_metadata(db, media.id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Vault metadata not found")

    encrypted_path, iv = metadata
    encrypted_file = Path(encrypted_path)
    if not encrypted_file.exists():
        raise HTTPException(status_code=404, detail="Encrypted vault blob not found")

    aad = build_vault_aad(media.id, media.file_hash)
    plaintext_file = _decrypt_to_temporary_path(
        master_key,
        iv,
        encrypted_file,
        associated_data=aad,
        prefix=f"vault-restore-{media.id}-",
    )

    original_key = media.minio_key
    content_type = media.content_type or "application/octet-stream"
    thumbnail_metadata: Optional[dict] = None
    staged_encrypted = encrypted_file.with_name(
        f".{encrypted_file.name}.{uuid4().hex}.restore-pending"
    )

    try:
        plaintext = plaintext_file.read_bytes()
        try:
            upload_file(plaintext, original_key, content_type)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail="Failed to restore image to configured storage",
            ) from exc

        try:
            thumbnail_metadata = upload_thumbnail(plaintext, media.file_hash)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to regenerate thumbnail for restored vault item")

        try:
            encrypted_file.replace(staged_encrypted)
        except Exception as exc:  # noqa: BLE001
            _delete_storage_objects_best_effort(
                original_key,
                thumbnail_metadata.get("thumbnail_key") if thumbnail_metadata else None,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to stage encrypted vault blob for restore",
            ) from exc

        try:
            db.execute(
                text("DELETE FROM vault_metadata WHERE media_id = :media_id"),
                {"media_id": media.id},
            )
            media.is_hidden = False
            media.vault_state = "visible"
            media.hidden_at = None
            media.encrypted_at = None
            _apply_thumbnail_metadata(media, thumbnail_metadata)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            try:
                staged_encrypted.replace(encrypted_file)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to restore staged encrypted vault blob")
            _delete_storage_objects_best_effort(
                original_key,
                thumbnail_metadata.get("thumbnail_key") if thumbnail_metadata else None,
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to commit restored image state",
            ) from exc

        encrypted_blob_removed = True
        try:
            staged_encrypted.unlink()
        except Exception:  # noqa: BLE001
            encrypted_blob_removed = False
            logger.exception("Restored vault item left an encrypted cleanup artifact")

        return {
            "status": "restored",
            "media_id": media.id,
            "encrypted_blob_removed": encrypted_blob_removed,
        }
    finally:
        plaintext_file.unlink(missing_ok=True)


@router.get("/vault/thumbnail/{media_id}")
def thumbnail_hidden_media(
    media_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Return a small authenticated preview without exposing the original."""
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
    plaintext_file = _decrypt_to_temporary_path(
        master_key,
        iv,
        encrypted_file,
        associated_data=aad,
        prefix=f"vault-thumbnail-{media.id}-",
    )
    try:
        thumbnail = _render_vault_thumbnail(plaintext_file)
    except (OSError, UnidentifiedImageError) as exc:
        raise HTTPException(
            status_code=422, detail="Vault image preview failed"
        ) from exc
    finally:
        plaintext_file.unlink(missing_ok=True)

    return Response(
        content=thumbnail,
        media_type=VAULT_THUMBNAIL_CONTENT_TYPE,
        headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
    )


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
        headers={"Cache-Control": "private, no-store", "Pragma": "no-cache"},
    )
