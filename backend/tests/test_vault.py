"""Tests for vault unlock, hide, stream, and listing behavior."""

import hashlib
import io
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from PIL import Image
import pytest
from sqlalchemy import text

from find_api.core import crypto
from find_api.core.crypto import SESSION_TTL_SECONDS
from find_api.main import app
from find_api.routers import vault as vault_router
from find_api.models.media import Media


def get_valid_image_bytes():
    """Generate a 1x1 valid PNG for testing."""
    img = Image.new("RGB", (1, 1), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def seed_media(db, *, filename: str = "vault-image.png") -> Media:
    """Insert a Media row into the test database."""
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/png",
        file_size=len(get_valid_image_bytes()),
        status="indexed",
        width=1,
        height=1,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def prepare_vault_tables(db) -> None:
    """Create and clear the vault tables used by the router."""
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS vault_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                salt BLOB NOT NULL,
                verifier_nonce BLOB NOT NULL,
                verifier_ciphertext BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS vault_metadata (
                media_id INTEGER PRIMARY KEY,
                encrypted_path TEXT NOT NULL,
                iv BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.execute(text("DELETE FROM vault_metadata"))
    db.execute(text("DELETE FROM vault_config"))
    db.commit()


@pytest.fixture()
def vault_artifacts():
    paths: list[Path] = []
    try:
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def unlock_vault(
    client, db, *, passphrase: str = "correct horse battery staple"
) -> str:
    """Unlock the vault and return the session token."""
    app.state.limiter.reset()
    vault_router.limiter.reset()
    prepare_vault_tables(db)
    response = client.post("/api/vault/unlock", json={"passphrase": passphrase})
    assert response.status_code == 200
    token = response.json()["session_token"]
    assert isinstance(token, str)
    assert token
    return token


def hide_media(client, db, *, media: Media, token: str) -> Path:
    """Hide a seeded media row using the vault endpoint."""
    with (
        patch(
            "find_api.routers.vault.download_file_to_path",
            side_effect=lambda _key, path: Path(path).write_bytes(
                get_valid_image_bytes()
            ),
        ),
        patch("find_api.routers.vault.delete_file"),
    ):
        response = client.post(
            "/api/vault/hide",
            json={"media_id": media.id},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    db.refresh(media)
    encrypted_path = db.execute(
        text("SELECT encrypted_path FROM vault_metadata WHERE media_id = :media_id"),
        {"media_id": media.id},
    ).scalar_one()
    return Path(encrypted_path)


class TestVaultUnlock:
    """Vault unlock endpoint behavior."""

    def test_unlock_happy_path(self, client, db):
        token = unlock_vault(client, db)
        assert token

    def test_unlock_blank_passphrase_rejected(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)
        response = client.post("/api/vault/unlock", json={"passphrase": ""})
        assert response.status_code == 400

        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)
        response = client.post("/api/vault/unlock", json={"passphrase": "   "})
        assert response.status_code == 400

    def test_unlock_wrong_passphrase_rejected_after_vault_initialized(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)
        response = client.post(
            "/api/vault/unlock",
            json={"passphrase": "correct horse battery staple"},
        )
        assert response.status_code == 200

        app.state.limiter.reset()
        vault_router.limiter.reset()
        response = client.post(
            "/api/vault/unlock",
            json={"passphrase": "wrong horse battery staple"},
        )
        assert response.status_code == 401


class TestVaultHide:
    """Vault hide endpoint behavior."""

    def test_hide_happy_path(self, client, db, vault_artifacts):
        media = seed_media(db)
        token = unlock_vault(client, db)

        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        assert media.is_hidden is True
        row = db.execute(
            text("SELECT 1 FROM vault_metadata WHERE media_id = :media_id"),
            {"media_id": media.id},
        ).first()
        assert row is not None

    def test_duplicate_hide_rejected(self, client, db, vault_artifacts):
        media = seed_media(db)
        token = unlock_vault(client, db)

        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        with (
            patch(
                "find_api.routers.vault.download_file_to_path",
                side_effect=lambda _key, path: Path(path).write_bytes(
                    get_valid_image_bytes()
                ),
            ),
            patch("find_api.routers.vault.delete_file"),
        ):
            response = client.post(
                "/api/vault/hide",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 409

    def test_invalid_session_token_rejected(self, client, db):
        media = seed_media(db)
        prepare_vault_tables(db)

        with (
            patch(
                "find_api.routers.vault.download_file_to_path",
                side_effect=lambda _key, path: Path(path).write_bytes(
                    get_valid_image_bytes()
                ),
            ),
            patch("find_api.routers.vault.delete_file"),
        ):
            response = client.post(
                "/api/vault/hide",
                json={"media_id": media.id},
                headers={"Authorization": "Bearer invalidtoken123"},
            )

        assert response.status_code == 401


class TestVaultStream:
    """Vault streaming endpoint behavior."""

    def test_expired_session_token_rejected(self, client, db, vault_artifacts):
        media = seed_media(db)
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        with crypto._sessions_lock:
            master_key, _created_at = crypto.active_vault_sessions[token]
            crypto.active_vault_sessions[token] = (
                master_key,
                time.time() - SESSION_TTL_SECONDS - 1,
            )

        response = client.get(
            f"/api/vault/stream/{media.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_stream_happy_path(self, client, db, vault_artifacts):
        media = seed_media(db, filename="stream.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        response = client.get(
            f"/api/vault/stream/{media.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
        assert response.content

    def test_tampered_gcm_tag_causes_decryption_error(
        self, client, db, vault_artifacts
    ):
        media = seed_media(db, filename="tamper.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        with encrypted_path.open("r+b") as handle:
            handle.seek(-16, os.SEEK_END)
            handle.write(os.urandom(16))

        with pytest.raises(InvalidTag):
            client.get(
                f"/api/vault/stream/{media.id}",
                headers={"Authorization": f"Bearer {token}"},
            )


class TestVaultGalleryIntegration:
    """Vault-hidden media should not appear in the public gallery."""

    def test_hidden_media_excluded_from_gallery(self, client, db, vault_artifacts):
        hidden_media = seed_media(db, filename="hidden.png")
        visible_media = seed_media(db, filename="visible.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=hidden_media, token=token)
        vault_artifacts.append(encrypted_path)

        response = client.get("/api/gallery")

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert hidden_media.id not in ids
        assert visible_media.id in ids
