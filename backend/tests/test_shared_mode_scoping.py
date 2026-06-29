"""Shared-mode ownership scoping tests (IDOR guard).

These verify that once an admin exists (shared mode), a regular member can
only see and mutate media they uploaded, an admin sees everything, and
unauthenticated requests are rejected. In local mode (no admin) the
endpoints stay permissive — that path is covered by the other test modules.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from find_api.core.auth import create_session, hash_password
from find_api.main import app
from find_api.models.media import Media
from find_api.models.user import User


@pytest.fixture(autouse=True)
def _use_real_auth_dependencies(client):
    """Use the genuine auth dependencies instead of conftest's local-mode stub."""
    from find_api.core.dependencies import get_admin_user, get_required_user

    removed = {}
    for dep in (get_required_user, get_admin_user):
        if dep in app.dependency_overrides:
            removed[dep] = app.dependency_overrides.pop(dep)
    yield
    app.dependency_overrides.update(removed)


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


def _seed_media(db, *, filename: str, uploader_user_id: int | None) -> Media:
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def shared_instance(db):
    """Seed an admin + two members with media, return tokens and media ids."""
    admin = _make_user(db, "admin", "admin")
    alice = _make_user(db, "alice", "member")
    bob = _make_user(db, "bob", "member")

    alice_media = _seed_media(db, filename="alice.jpg", uploader_user_id=alice.id)
    bob_media = _seed_media(db, filename="bob.jpg", uploader_user_id=bob.id)

    admin_token, _ = create_session(db, admin.id)
    alice_token, _ = create_session(db, alice.id)
    bob_token, _ = create_session(db, bob.id)

    return {
        "admin_token": admin_token,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "alice_media": alice_media.id,
        "bob_media": bob_media.id,
    }


class TestGalleryScoping:
    def test_member_sees_only_own_media(self, client, shared_instance):
        resp = client.get("/api/gallery", headers=_auth(shared_instance["alice_token"]))
        assert resp.status_code == 200
        body = resp.json()
        ids = {item["id"] for item in body["items"]}
        assert ids == {shared_instance["alice_media"]}
        assert body["total"] == 1

    def test_admin_sees_all_media(self, client, shared_instance):
        resp = client.get("/api/gallery", headers=_auth(shared_instance["admin_token"]))
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert ids == {shared_instance["alice_media"], shared_instance["bob_media"]}

    def test_unauthenticated_request_is_rejected(self, client, shared_instance):
        resp = client.get("/api/gallery")
        assert resp.status_code == 401

    def test_counts_are_scoped(self, client, shared_instance):
        resp = client.get(
            "/api/gallery/counts", headers=_auth(shared_instance["bob_token"])
        )
        assert resp.status_code == 200
        assert resp.json()["all"] == 1


class TestImageDetailScoping:
    def test_member_cannot_read_others_image(self, client, shared_instance):
        resp = client.get(
            f"/api/image/{shared_instance['bob_media']}",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 404

    def test_member_can_read_own_image(self, client, shared_instance):
        resp = client.get(
            f"/api/image/{shared_instance['alice_media']}",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == shared_instance["alice_media"]

    def test_admin_can_read_any_image(self, client, shared_instance):
        resp = client.get(
            f"/api/image/{shared_instance['bob_media']}",
            headers=_auth(shared_instance["admin_token"]),
        )
        assert resp.status_code == 200


class TestDeleteScoping:
    def test_member_cannot_delete_others_image(self, client, shared_instance):
        resp = client.delete(
            f"/api/image/{shared_instance['bob_media']}",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 404

    def test_member_can_delete_own_image(self, client, shared_instance):
        resp = client.delete(
            f"/api/image/{shared_instance['alice_media']}",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 200


class TestAdminOnlyEndpoints:
    def test_member_cannot_reset_search_preferences(self, client, shared_instance):
        resp = client.delete(
            "/api/feedback/search-preferences",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 403

    def test_admin_can_reset_search_preferences(self, client, shared_instance):
        resp = client.delete(
            "/api/feedback/search-preferences",
            headers=_auth(shared_instance["admin_token"]),
        )
        assert resp.status_code == 200


class TestAlbumScoping:
    """Albums must not let a member pull in or read back another user's media."""

    def test_member_cannot_add_others_media_to_album(self, client, shared_instance):
        # Alice creates an album she owns.
        created = client.post(
            "/api/albums",
            json={"name": "Alice album"},
            headers=_auth(shared_instance["alice_token"]),
        )
        assert created.status_code == 200
        album_id = created.json()["id"]

        # She tries to add BOB's media id (IDOR attempt).
        resp = client.put(
            f"/api/albums/{album_id}/assets",
            json={"media_ids": [shared_instance["bob_media"]]},
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Bob's media must be rejected (skipped), not added.
        assert body["added_ids"] == []
        assert shared_instance["bob_media"] in body["skipped_ids"]

        # And it must not be readable back through the album.
        listing = client.get(
            f"/api/albums/{album_id}/assets",
            headers=_auth(shared_instance["alice_token"]),
        )
        assert listing.status_code == 200
        assert listing.json()["items"] == []

    def test_member_cannot_read_or_mutate_others_album(self, client, shared_instance):
        # Bob creates an album.
        created = client.post(
            "/api/albums",
            json={"name": "Bob album"},
            headers=_auth(shared_instance["bob_token"]),
        )
        bob_album = created.json()["id"]

        # Alice cannot read it (404, existence masked).
        assert (
            client.get(
                f"/api/albums/{bob_album}",
                headers=_auth(shared_instance["alice_token"]),
            ).status_code
            == 404
        )
        # Alice cannot delete it.
        assert (
            client.delete(
                f"/api/albums/{bob_album}",
                headers=_auth(shared_instance["alice_token"]),
            ).status_code
            == 404
        )

    def test_member_can_add_own_media_to_album(self, client, shared_instance):
        created = client.post(
            "/api/albums",
            json={"name": "Alice album"},
            headers=_auth(shared_instance["alice_token"]),
        )
        album_id = created.json()["id"]

        resp = client.put(
            f"/api/albums/{album_id}/assets",
            json={"media_ids": [shared_instance["alice_media"]]},
            headers=_auth(shared_instance["alice_token"]),
        )
        assert resp.json()["added_ids"] == [shared_instance["alice_media"]]
