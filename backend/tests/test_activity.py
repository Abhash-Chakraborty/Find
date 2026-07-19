"""Tests for the local activity log: recording, listing, retention, and IDOR.

Mirrors test_shared_mode_scoping.py / test_partner_sharing.py for the
multi-user scoping tests.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from find_api.core.auth import create_session, hash_password
from find_api.core.config import settings
from find_api.main import app
from find_api.models.activity import Activity
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers import vault as vault_router
from find_api.services.activity_log import record_activity


def _seed_media(db, *, filename: str = "photo.jpg", uploader_user_id=None) -> Media:
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        uploader_user_id=uploader_user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _make_user(db, username: str, role: str) -> User:
    user = User(
        username=username,
        display_name=username,
        password_hash=hash_password("s3cure!pass"),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _prepare_vault_tables(db) -> None:
    """Create the vault tables the router expects (mirrors test_vault.py)."""
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS vault_config ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), salt BLOB NOT NULL, "
            "verifier_nonce BLOB NOT NULL, verifier_ciphertext BLOB NOT NULL, "
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS vault_metadata ("
            "media_id INTEGER PRIMARY KEY, encrypted_path TEXT NOT NULL, "
            "iv BLOB NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    db.execute(text("DELETE FROM vault_metadata"))
    db.execute(text("DELETE FROM vault_config"))
    db.commit()


class TestVaultEvents:
    def test_unlock_lock_record_activity(self, client, db):
        app.state.limiter.reset()
        vault_router.limiter.reset()
        _prepare_vault_tables(db)

        first = client.post(
            "/api/vault/unlock", json={"passphrase": "correct horse battery"}
        )
        assert first.status_code == 200
        second = client.post(
            "/api/vault/unlock", json={"passphrase": "correct horse battery"}
        )
        assert second.status_code == 200
        client.post(
            "/api/vault/lock", json={"session_token": second.json()["session_token"]}
        )

        actions = [a.action for a in db.query(Activity).order_by(Activity.id).all()]
        assert actions == ["created", "unlocked", "locked"]
        assert all(a.category == "vault" for a in db.query(Activity).all())

    def test_restore_records_activity(self, client, db):
        """Covers the protected-storage-mode restore path (no encrypted blob)."""
        app.state.limiter.reset()
        vault_router.limiter.reset()
        _prepare_vault_tables(db)

        media = _seed_media(db)
        token = client.post(
            "/api/vault/unlock", json={"passphrase": "correct horse battery"}
        ).json()["session_token"]

        # Mirrors what the hide endpoint's protected-storage branch sets,
        # without going through hide itself (out of scope for this hook).
        media.is_hidden = True
        media.vault_state = "hidden"
        media.hidden_at = datetime.now(timezone.utc)
        db.commit()

        resp = client.post(
            "/api/vault/restore", json={"media_id": media.id}, headers=_auth(token)
        )
        assert resp.status_code == 200
        row = db.query(Activity).filter(Activity.action == "restored").one()
        assert row.category == "vault"
        assert row.media_id == media.id


class TestRecordActivity:
    def test_writes_row_with_fields(self, db):
        record_activity(
            db, "media", "trashed", user_id=None, media_id=1, payload={"a": 1}
        )
        row = db.query(Activity).one()
        assert row.category == "media"
        assert row.action == "trashed"
        assert row.media_id == 1
        assert row.payload == {"a": 1}

    def test_never_raises_on_failure(self):
        broken_db = MagicMock()
        broken_db.add.side_effect = RuntimeError("boom")
        record_activity(broken_db, "media", "trashed")  # must not raise
        broken_db.rollback.assert_called_once()


class TestArchiveTrashRestoreEvents:
    def test_archive_and_unarchive_record_activity(self, client, db):
        media = _seed_media(db)
        client.post(f"/api/image/{media.id}/archive", json={"archived": True})
        client.post(f"/api/image/{media.id}/archive", json={"archived": False})
        actions = [a.action for a in db.query(Activity).order_by(Activity.id).all()]
        assert actions == ["archived", "unarchived"]

    def test_trash_and_restore_record_activity(self, client, db):
        media = _seed_media(db)
        client.post(f"/api/image/{media.id}/trash")
        client.post(f"/api/image/{media.id}/restore")
        row = db.query(Activity).filter(Activity.action == "trashed").one()
        assert row.media_id == media.id
        assert db.query(Activity).filter(Activity.action == "restored").count() == 1

    def test_repeated_trash_is_not_double_logged(self, client, db):
        media = _seed_media(db)
        client.post(f"/api/image/{media.id}/trash")
        client.post(f"/api/image/{media.id}/trash")
        assert db.query(Activity).filter(Activity.action == "trashed").count() == 1


class TestSettingsEvents:
    def test_change_records_activity(self, client, db):
        resp = client.put("/api/settings", json={"accel_mode": "gpu"})
        assert resp.status_code == 200
        row = db.query(Activity).filter(Activity.category == "settings").one()
        assert row.action == "updated"
        assert row.payload == {"key": "accel_mode", "from": "auto", "to": "gpu"}

    def test_no_op_does_not_record(self, client, db):
        client.put("/api/settings", json={"accel_mode": "auto"})
        assert db.query(Activity).count() == 0


class TestListActivity:
    def test_pagination_and_newest_first(self, client, db):
        for i in range(3):
            record_activity(db, "media", "trashed", media_id=i)
        resp = client.get("/api/activity?limit=2")
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["items"][0]["media_id"] == 2

    def test_filter_by_category_and_action(self, client, db):
        record_activity(db, "vault", "locked")
        record_activity(db, "media", "trashed")
        items = client.get("/api/activity?category=vault").json()["items"]
        assert len(items) == 1 and items[0]["action"] == "locked"

    def test_filter_by_media_id(self, client, db):
        record_activity(db, "media", "trashed", media_id=5)
        record_activity(db, "media", "trashed", media_id=6)
        items = client.get("/api/activity?media_id=5").json()["items"]
        assert [i["media_id"] for i in items] == [5]


class TestClearAndPurge:
    def test_clear_deletes_everything_in_scope(self, client, db):
        record_activity(db, "media", "trashed")
        resp = client.post("/api/activity/clear")
        assert resp.json()["deleted_count"] == 1
        assert db.query(Activity).count() == 0

    def test_purge_deletes_only_rows_past_retention(self, client, db):
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                Activity(
                    category="media",
                    action="trashed",
                    created_at=now
                    - timedelta(days=settings.ACTIVITY_RETENTION_DAYS + 1),
                ),
                Activity(category="media", action="trashed", created_at=now),
            ]
        )
        db.commit()
        resp = client.post("/api/activity/purge")
        assert resp.json()["deleted_count"] == 1
        assert db.query(Activity).count() == 1

    def test_purge_disabled_when_retention_zero(self, client, db, monkeypatch):
        monkeypatch.setattr(settings, "ACTIVITY_RETENTION_DAYS", 0)
        record_activity(db, "media", "trashed")
        db.query(Activity).update(
            {Activity.created_at: datetime(2000, 1, 1, tzinfo=timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
        resp = client.post("/api/activity/purge")
        assert resp.json()["deleted_count"] == 0
        assert db.query(Activity).count() == 1


class TestActivityScoping:
    """Shared-mode IDOR: a member only sees/clears their own activity."""

    @pytest.fixture(autouse=True)
    def _use_real_auth_dependencies(self, client):
        from find_api.core.dependencies import get_admin_user, get_required_user

        removed = {}
        for dep in (get_required_user, get_admin_user):
            if dep in app.dependency_overrides:
                removed[dep] = app.dependency_overrides.pop(dep)
        yield
        app.dependency_overrides.update(removed)

    @pytest.fixture()
    def shared_instance(self, db):
        admin = _make_user(db, "admin", "admin")
        alice = _make_user(db, "alice", "member")
        bob = _make_user(db, "bob", "member")
        record_activity(db, "media", "trashed", user_id=alice.id)
        record_activity(db, "media", "trashed", user_id=bob.id)
        return {
            "admin_token": create_session(db, admin.id)[0],
            "alice_token": create_session(db, alice.id)[0],
            "bob_token": create_session(db, bob.id)[0],
        }

    def test_member_sees_only_own_activity(self, client, shared_instance):
        resp = client.get(
            "/api/activity", headers=_auth(shared_instance["alice_token"])
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_admin_sees_all_activity(self, client, shared_instance):
        resp = client.get(
            "/api/activity", headers=_auth(shared_instance["admin_token"])
        )
        assert resp.json()["total"] == 2

    def test_unauthenticated_request_is_rejected(self, client, shared_instance):
        assert client.get("/api/activity").status_code == 401

    def test_member_clear_does_not_touch_others_rows(self, client, shared_instance):
        resp = client.post(
            "/api/activity/clear", headers=_auth(shared_instance["alice_token"])
        )
        assert resp.json()["deleted_count"] == 1
        remaining = client.get(
            "/api/activity", headers=_auth(shared_instance["admin_token"])
        ).json()
        assert remaining["total"] == 1
