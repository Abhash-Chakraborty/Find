"""Tests for vault unlock, hide, stream, and listing behavior."""

import hashlib
import io
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, call, patch

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


def seed_media(
    db, *, filename: str = "vault-image.png", with_thumbnail: bool = False
) -> Media:
    """Insert a Media row into the test database."""
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/png",
        file_size=len(get_valid_image_bytes()),
        thumbnail_key=(f"thumbnails/test/{filename}.webp" if with_thumbnail else None),
        thumbnail_content_type="image/webp" if with_thumbnail else None,
        thumbnail_size=123 if with_thumbnail else None,
        thumbnail_width=1 if with_thumbnail else None,
        thumbnail_height=1 if with_thumbnail else None,
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
    """Hide through the legacy encrypted path to retain migration coverage."""
    db.execute(text("UPDATE vault_config SET storage_mode = 'encrypted' WHERE id = 1"))
    db.commit()
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


class TestVaultCredentials:
    """Setup and recovery rotate credentials without exposing stored secrets."""

    def test_setup_status_and_recovery_round_trip(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)

        status = client.get("/api/vault/status")
        assert status.status_code == 200
        assert status.json() == {
            "initialized": False,
            "recovery_available": False,
        }

        setup = client.post(
            "/api/vault/setup",
            json={"passphrase": "initial local password"},
        )
        assert setup.status_code == 200
        recovery_code = setup.json()["recovery_code"]
        assert recovery_code
        assert setup.json()["session_token"]

        stored_hash = db.execute(
            text("SELECT recovery_code_hash FROM vault_config WHERE id = 1")
        ).scalar_one()
        assert stored_hash
        assert recovery_code not in stored_hash

        status = client.get("/api/vault/status")
        assert status.json() == {
            "initialized": True,
            "recovery_available": True,
        }

        recovered = client.post(
            "/api/vault/recover",
            json={
                "recovery_code": recovery_code.lower(),
                "new_passphrase": "replacement local password",
            },
        )
        assert recovered.status_code == 200
        assert recovered.json()["session_token"]
        assert recovered.json()["recovery_code"] != recovery_code

        app.state.limiter.reset()
        vault_router.limiter.reset()
        old_unlock = client.post(
            "/api/vault/unlock",
            json={"passphrase": "initial local password"},
        )
        assert old_unlock.status_code == 401

        app.state.limiter.reset()
        vault_router.limiter.reset()
        new_unlock = client.post(
            "/api/vault/unlock",
            json={"passphrase": "replacement local password"},
        )
        assert new_unlock.status_code == 200

    def test_password_change_rotates_credentials_round_trip(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)
        setup = client.post(
            "/api/vault/setup",
            json={"passphrase": "initial local password"},
        )
        assert setup.status_code == 200
        previous_hash = db.execute(
            text("SELECT recovery_code_hash FROM vault_config WHERE id = 1")
        ).scalar_one()

        app.state.limiter.reset()
        vault_router.limiter.reset()
        changed = client.post(
            "/api/vault/password",
            json={
                "current_passphrase": "initial local password",
                "new_passphrase": "replacement local password",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["session_token"]
        assert changed.json()["recovery_code"]
        rotated_hash = db.execute(
            text("SELECT recovery_code_hash FROM vault_config WHERE id = 1")
        ).scalar_one()
        assert rotated_hash != previous_hash
        assert changed.json()["recovery_code"] not in rotated_hash

        app.state.limiter.reset()
        vault_router.limiter.reset()
        assert (
            client.post(
                "/api/vault/unlock",
                json={"passphrase": "initial local password"},
            ).status_code
            == 401
        )

        app.state.limiter.reset()
        vault_router.limiter.reset()
        assert (
            client.post(
                "/api/vault/unlock",
                json={"passphrase": "replacement local password"},
            ).status_code
            == 200
        )

    def test_legacy_migration_failure_does_not_block_credentials(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        prepare_vault_tables(db)
        assert (
            client.post(
                "/api/vault/setup",
                json={"passphrase": "initial local password"},
            ).status_code
            == 200
        )

        app.state.limiter.reset()
        vault_router.limiter.reset()
        with patch.object(
            vault_router,
            "_migrate_legacy_encrypted_items",
            side_effect=RuntimeError("corrupt legacy blob"),
        ):
            unlocked = client.post(
                "/api/vault/unlock",
                json={"passphrase": "initial local password"},
            )
        assert unlocked.status_code == 200

        app.state.limiter.reset()
        vault_router.limiter.reset()
        with patch.object(
            vault_router,
            "_migrate_legacy_encrypted_items",
            side_effect=RuntimeError("missing legacy blob"),
        ):
            changed = client.post(
                "/api/vault/password",
                json={
                    "current_passphrase": "initial local password",
                    "new_passphrase": "replacement local password",
                },
            )
        assert changed.status_code == 200

        app.state.limiter.reset()
        vault_router.limiter.reset()
        assert (
            client.post(
                "/api/vault/unlock",
                json={"passphrase": "replacement local password"},
            ).status_code
            == 200
        )


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

    def test_hide_removes_plaintext_original_and_thumbnail(
        self, client, db, vault_artifacts
    ):
        media = seed_media(db, filename="with-thumb.png", with_thumbnail=True)
        token = unlock_vault(client, db)
        db.execute(
            text("UPDATE vault_config SET storage_mode = 'encrypted' WHERE id = 1")
        )
        db.commit()
        delete_mock = Mock()

        with (
            patch(
                "find_api.routers.vault.download_file_to_path",
                side_effect=lambda _key, path: Path(path).write_bytes(
                    get_valid_image_bytes()
                ),
            ),
            patch("find_api.routers.vault.delete_file", delete_mock),
        ):
            response = client.post(
                "/api/vault/hide",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        encrypted_path = Path(
            db.execute(
                text(
                    "SELECT encrypted_path FROM vault_metadata "
                    "WHERE media_id = :media_id"
                ),
                {"media_id": media.id},
            ).scalar_one()
        )
        vault_artifacts.append(encrypted_path)
        assert delete_mock.call_args_list == [
            call(media.minio_key),
            call(media.thumbnail_key),
        ]

    def test_protected_storage_hide_keeps_private_objects(self, client, db):
        media = seed_media(db, filename="protected.png", with_thumbnail=True)
        token = unlock_vault(client, db)
        delete_mock = Mock()
        with patch("find_api.routers.vault.delete_file", delete_mock):
            response = client.post(
                "/api/vault/hide",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        assert response.json()["storage_mode"] == "protected"
        db.refresh(media)
        assert media.is_hidden is True
        assert media.vault_state == "hidden"
        assert (
            db.execute(
                text("SELECT 1 FROM vault_metadata WHERE media_id = :media_id"),
                {"media_id": media.id},
            ).first()
            is None
        )
        delete_mock.assert_not_called()


class TestVaultLock:
    """Locking invalidates the in-memory key immediately."""

    def test_lock_invalidates_session(self, client, db):
        token = unlock_vault(client, db)

        response = client.post(
            "/api/vault/lock",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "locked"}

        response = client.get(
            "/api/vault/list",
            headers={"Authorization": f"Bearer {token}"},
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

    def test_swapped_encrypted_blob_rejected(self, client, db, vault_artifacts):
        first_media = seed_media(db, filename="first-vault.png")
        second_media = seed_media(db, filename="second-vault.png")
        token = unlock_vault(client, db)

        first_encrypted_path = hide_media(client, db, media=first_media, token=token)
        second_encrypted_path = hide_media(client, db, media=second_media, token=token)
        vault_artifacts.extend([first_encrypted_path, second_encrypted_path])

        second_metadata = db.execute(
            text(
                "SELECT encrypted_path, iv "
                "FROM vault_metadata WHERE media_id = :media_id"
            ),
            {"media_id": second_media.id},
        ).one()
        db.execute(
            text(
                "UPDATE vault_metadata SET encrypted_path = :encrypted_path, iv = :iv "
                "WHERE media_id = :media_id"
            ),
            {
                "media_id": first_media.id,
                "encrypted_path": second_metadata.encrypted_path,
                "iv": second_metadata.iv,
            },
        )
        db.commit()

        with pytest.raises(InvalidTag):
            client.get(
                f"/api/vault/stream/{first_media.id}",
                headers={"Authorization": f"Bearer {token}"},
            )

    def test_tampered_authenticated_metadata_rejected(
        self, client, db, vault_artifacts
    ):
        media = seed_media(db, filename="metadata-tamper.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        media.file_hash = hashlib.sha256(b"tampered-metadata").hexdigest()
        db.commit()

        with pytest.raises(InvalidTag):
            client.get(
                f"/api/vault/stream/{media.id}",
                headers={"Authorization": f"Bearer {token}"},
            )


class TestVaultThumbnail:
    """Vault timeline previews are bounded and session protected."""

    def test_thumbnail_happy_path(self, client, db, vault_artifacts):
        media = seed_media(db, filename="thumbnail.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        response = client.get(
            f"/api/vault/thumbnail/{media.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/webp")
        assert response.headers["cache-control"] == "private, no-store"
        with Image.open(io.BytesIO(response.content)) as thumbnail:
            assert thumbnail.width <= vault_router.VAULT_THUMBNAIL_MAX_SIZE[0]
            assert thumbnail.height <= vault_router.VAULT_THUMBNAIL_MAX_SIZE[1]

    def test_thumbnail_rejects_invalid_session(self, client, db):
        media = seed_media(db, filename="locked-thumbnail.png")
        prepare_vault_tables(db)

        response = client.get(
            f"/api/vault/thumbnail/{media.id}",
            headers={"Authorization": "Bearer not-a-vault-session"},
        )

        assert response.status_code == 401


class TestVaultRestore:
    """Restore keeps the encrypted rollback source until storage and DB succeed."""

    def test_restore_happy_path(self, client, db, vault_artifacts):
        media = seed_media(db, filename="restore.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)
        uploaded: dict[str, object] = {}

        def capture_upload(data, object_name, content_type):
            uploaded.update(
                data=data,
                object_name=object_name,
                content_type=content_type,
            )
            return object_name

        thumbnail_metadata = {
            "thumbnail_key": "thumbnails/restored.webp",
            "thumbnail_content_type": "image/webp",
            "thumbnail_size": 42,
            "thumbnail_width": 1,
            "thumbnail_height": 1,
        }
        with (
            patch("find_api.routers.vault.upload_file", side_effect=capture_upload),
            patch(
                "find_api.routers.vault.upload_thumbnail",
                return_value=thumbnail_metadata,
            ),
        ):
            response = client.post(
                "/api/vault/restore",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "status": "restored",
            "media_id": media.id,
            "encrypted_blob_removed": True,
        }
        assert uploaded["data"] == get_valid_image_bytes()
        assert uploaded["object_name"] == media.minio_key
        assert uploaded["content_type"] == "image/png"
        db.refresh(media)
        assert media.is_hidden is False
        assert media.vault_state == "visible"
        assert media.hidden_at is None
        assert media.encrypted_at is None
        assert media.thumbnail_key == thumbnail_metadata["thumbnail_key"]
        assert (
            db.execute(
                text("SELECT 1 FROM vault_metadata WHERE media_id = :media_id"),
                {"media_id": media.id},
            ).first()
            is None
        )
        assert not encrypted_path.exists()

    def test_storage_failure_keeps_encrypted_item_hidden(
        self, client, db, vault_artifacts
    ):
        media = seed_media(db, filename="restore-storage-failure.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        with patch(
            "find_api.routers.vault.upload_file", side_effect=RuntimeError("offline")
        ):
            response = client.post(
                "/api/vault/restore",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 500
        db.refresh(media)
        assert media.is_hidden is True
        assert media.vault_state == "hidden_encrypted"
        assert encrypted_path.exists()
        assert db.execute(
            text("SELECT 1 FROM vault_metadata WHERE media_id = :media_id"),
            {"media_id": media.id},
        ).first()

    def test_database_failure_restores_encrypted_blob_and_cleans_replacement(
        self, client, db, vault_artifacts
    ):
        media = seed_media(db, filename="restore-db-failure.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=media, token=token)
        vault_artifacts.append(encrypted_path)

        with (
            patch("find_api.routers.vault.upload_file", return_value=media.minio_key),
            patch("find_api.routers.vault.upload_thumbnail", return_value=None),
            patch("find_api.routers.vault.delete_file") as delete_mock,
            patch(
                "find_api.routers.vault.Session.commit",
                side_effect=RuntimeError("db offline"),
            ),
        ):
            response = client.post(
                "/api/vault/restore",
                json={"media_id": media.id},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 500
        db.refresh(media)
        assert media.is_hidden is True
        assert media.vault_state == "hidden_encrypted"
        assert encrypted_path.exists()
        assert db.execute(
            text("SELECT 1 FROM vault_metadata WHERE media_id = :media_id"),
            {"media_id": media.id},
        ).first()
        delete_mock.assert_called_once_with(media.minio_key)


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

    def test_vault_list_does_not_expose_encryption_material(
        self, client, db, vault_artifacts
    ):
        hidden_media = seed_media(db, filename="secret.png")
        token = unlock_vault(client, db)
        encrypted_path = hide_media(client, db, media=hidden_media, token=token)
        vault_artifacts.append(encrypted_path)

        response = client.get(
            "/api/vault/list",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        item = response.json()[0]
        assert "encrypted_path" not in item
        assert "iv" not in item
        assert "verifier_ciphertext" not in item
        assert "salt" not in item
