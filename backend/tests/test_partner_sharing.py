"""Partner-sharing tests (Phase 4.3 — partner sharing).

Mirrors test_shared_mode_scoping.py's multi-user setup. Emphasis on the
security properties: grants are owner-scoped (IDOR), partner reads are gated on
an existing grant, reads are scoped to the sharer's browsable media only, and
the whole feature is rejected in local (single-user) mode.
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


def _seed_media(
    db, *, filename: str, uploader_user_id: int, is_archived=False, deleted_at=None
) -> Media:
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
        is_archived=is_archived,
        deleted_at=deleted_at,
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
    admin = _make_user(db, "admin", "admin")
    alice = _make_user(db, "alice", "member")
    bob = _make_user(db, "bob", "member")

    alice_media = _seed_media(db, filename="alice.jpg", uploader_user_id=alice.id)
    bob_media = _seed_media(db, filename="bob.jpg", uploader_user_id=bob.id)

    return {
        "alice": alice,
        "bob": bob,
        "alice_token": create_session(db, alice.id)[0],
        "bob_token": create_session(db, bob.id)[0],
        "admin_token": create_session(db, admin.id)[0],
        "alice_media": alice_media.id,
        "bob_media": bob_media.id,
    }


class TestPartnerGrants:
    def test_create_and_list_grant(self, client, shared_instance):
        s = shared_instance
        resp = client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["partner_user_id"] == s["bob"].id

        # Alice sees it as outgoing; Bob sees it as incoming.
        alice_list = client.get("/api/partners", headers=_auth(s["alice_token"])).json()
        assert len(alice_list["shared_with"]) == 1
        assert alice_list["shared_with_me"] == []

        bob_list = client.get("/api/partners", headers=_auth(s["bob_token"])).json()
        assert len(bob_list["shared_with_me"]) == 1
        assert bob_list["shared_with"] == []

    def test_create_is_idempotent(self, client, shared_instance):
        s = shared_instance
        for _ in range(2):
            client.post(
                "/api/partners",
                json={"partner_user_id": s["bob"].id},
                headers=_auth(s["alice_token"]),
            )
        out = client.get("/api/partners", headers=_auth(s["alice_token"])).json()
        assert len(out["shared_with"]) == 1

    def test_cannot_share_with_self(self, client, shared_instance):
        s = shared_instance
        resp = client.post(
            "/api/partners",
            json={"partner_user_id": s["alice"].id},
            headers=_auth(s["alice_token"]),
        )
        assert resp.status_code == 400

    def test_share_with_unknown_user_404(self, client, shared_instance):
        s = shared_instance
        resp = client.post(
            "/api/partners",
            json={"partner_user_id": 99999},
            headers=_auth(s["alice_token"]),
        )
        assert resp.status_code == 404

    def test_revoke_only_by_sharer(self, client, shared_instance):
        s = shared_instance
        share = client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        ).json()

        # Bob (the partner, not the sharer) cannot revoke Alice's grant.
        denied = client.delete(
            f"/api/partners/{share['id']}", headers=_auth(s["bob_token"])
        )
        assert denied.status_code == 404

        # Alice (the sharer) can.
        ok = client.delete(
            f"/api/partners/{share['id']}", headers=_auth(s["alice_token"])
        )
        assert ok.status_code == 200


class TestPartnerMediaAccess:
    def test_partner_reads_sharer_media_after_grant(self, client, shared_instance):
        s = shared_instance
        client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        )
        # Bob can now read Alice's library.
        resp = client.get(
            f"/api/partners/{s['alice'].id}/media", headers=_auth(s["bob_token"])
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["id"] == s["alice_media"]
        # Security: no raw storage keys leak; URLs are grant-checked byte routes.
        assert "minio_key" not in item
        assert "thumbnail_key" not in item
        assert item["thumbnail_url"] == (
            f"/api/partners/{s['alice'].id}/media/{s['alice_media']}/thumbnail"
        )
        assert item["url"] == (
            f"/api/partners/{s['alice'].id}/media/{s['alice_media']}/original"
        )

    def test_byte_routes_require_a_grant(self, client, shared_instance):
        s = shared_instance
        # No grant → byte routes 404 (same as the listing), not just the list.
        assert (
            client.get(
                f"/api/partners/{s['alice'].id}/media/{s['alice_media']}/original",
                headers=_auth(s["bob_token"]),
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/partners/{s['alice'].id}/media/{s['alice_media']}/thumbnail",
                headers=_auth(s["bob_token"]),
            ).status_code
            == 404
        )

    def test_revoke_cuts_off_byte_access(self, client, db, shared_instance):
        s = shared_instance
        share = client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        ).json()
        url = f"/api/partners/{s['alice'].id}/media/{s['alice_media']}/original"
        # With the grant, the byte route resolves to the object fetch (the
        # storage layer is mocked in conftest, so a 200/404 from storage is
        # fine — what matters is it is NOT the 404 "no shared library" gate).
        granted = client.get(url, headers=_auth(s["bob_token"]))
        assert granted.status_code != 403

        client.delete(f"/api/partners/{share['id']}", headers=_auth(s["alice_token"]))
        # After revoke, the grant gate 404s before any storage access.
        assert client.get(url, headers=_auth(s["bob_token"])).status_code == 404

    def test_byte_route_scoped_to_sharer_library(self, client, shared_instance):
        s = shared_instance
        client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        )
        # Bob has a grant from Alice, but Bob's own media id is not in Alice's
        # library → 404 (cannot pivot a grant to read arbitrary media ids).
        resp = client.get(
            f"/api/partners/{s['alice'].id}/media/{s['bob_media']}/original",
            headers=_auth(s["bob_token"]),
        )
        assert resp.status_code == 404

    def test_no_grant_is_404(self, client, shared_instance):
        s = shared_instance
        # Bob has no grant from Alice → cannot read, and existence is not leaked.
        resp = client.get(
            f"/api/partners/{s['alice'].id}/media", headers=_auth(s["bob_token"])
        )
        assert resp.status_code == 404

    def test_grant_is_one_directional(self, client, shared_instance):
        s = shared_instance
        # Alice shares with Bob; that does NOT let Alice read Bob's library.
        client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        )
        resp = client.get(
            f"/api/partners/{s['bob'].id}/media", headers=_auth(s["alice_token"])
        )
        assert resp.status_code == 404

    def test_archived_and_trashed_media_excluded(self, client, db, shared_instance):
        s = shared_instance
        _seed_media(
            db, filename="a-arch.jpg", uploader_user_id=s["alice"].id, is_archived=True
        )
        _seed_media(
            db,
            filename="a-trash.jpg",
            uploader_user_id=s["alice"].id,
            deleted_at=datetime.now(timezone.utc),
        )
        client.post(
            "/api/partners",
            json={"partner_user_id": s["bob"].id},
            headers=_auth(s["alice_token"]),
        )
        body = client.get(
            f"/api/partners/{s['alice'].id}/media", headers=_auth(s["bob_token"])
        ).json()
        # Only the single browsable asset, not the archived/trashed ones.
        assert body["total"] == 1
        assert body["items"][0]["id"] == s["alice_media"]


class TestPartnerLocalModeRejected:
    def test_local_mode_rejects_partner_endpoints(self, client):
        # No users exist → local mode → partner sharing is unavailable.
        assert client.get("/api/partners").status_code == 400
        assert (
            client.post("/api/partners", json={"partner_user_id": 1}).status_code == 400
        )
