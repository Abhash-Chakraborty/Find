"""Integration tests for shared-link endpoints (Phase 4.3).

Emphasis on the security properties: keys are stored hashed (not plaintext),
passwords are required + verified, expiry is enforced, public access is scoped
to exactly the linked album, and originals are gated on allow_download.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from find_api.core.auth import hash_token
from find_api.models.album import AlbumAsset
from find_api.models.media import Media
from find_api.models.shared_link import SharedLink


def _seed_media(db, *, filename, is_archived=False, deleted_at=None):
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        is_hidden=False,
        is_archived=is_archived,
        deleted_at=deleted_at,
        vault_state="visible",
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _make_album_with_assets(client, db, filenames):
    album = client.post("/api/albums", json={"name": "Shared"}).json()
    media = [_seed_media(db, filename=f) for f in filenames]
    client.put(
        f"/api/albums/{album['id']}/assets",
        json={"media_ids": [m.id for m in media]},
    )
    return album, media


def _create_link(client, album_id, **kwargs):
    payload = {"album_id": album_id, **kwargs}
    response = client.post("/api/shared-links", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


class TestSharedLinkSecurity:
    def test_key_is_not_stored_in_plaintext(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])
        raw_key = link["key"]

        row = db.query(SharedLink).filter(SharedLink.id == link["id"]).first()
        # Only the hash is persisted; the raw key never appears in the DB.
        assert row.key_hash == hash_token(raw_key)
        assert raw_key not in (row.key_hash or "")
        assert row.key_hash != raw_key

    def test_password_is_hashed_not_plaintext(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], password="hunter2")

        row = db.query(SharedLink).filter(SharedLink.id == link["id"]).first()
        assert row.password_hash is not None
        assert row.password_hash != "hunter2"
        assert "hunter2" not in row.password_hash
        # bcrypt hashes start with $2.
        assert row.password_hash.startswith("$2")

    def test_create_response_exposes_key_once(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])
        assert "key" in link and link["url"].endswith(link["key"])
        # Listing never re-exposes the key.
        listed = client.get("/api/shared-links").json()["shared_links"]
        assert all("key" not in item for item in listed)


class TestSharedLinkPublicAccess:
    def test_public_access_returns_only_album_assets(self, client, db):
        album, media = _make_album_with_assets(client, db, ["a.jpg", "b.jpg"])
        # An asset NOT in the album must never appear via the link.
        _seed_media(db, filename="outside.jpg")
        link = _create_link(client, album["id"])

        body = client.get(f"/api/public/shared/{link['key']}").json()
        names = {item["filename"] for item in body["items"]}
        assert names == {"a.jpg", "b.jpg"}
        assert body["total"] == 2

    def test_unknown_key_returns_404(self, client):
        assert client.get("/api/public/shared/bogus-key").status_code == 404

    def test_archived_trashed_excluded_from_public_view(self, client, db):
        album = client.post("/api/albums", json={"name": "X"}).json()
        visible = _seed_media(db, filename="vis.jpg")
        client.put(
            f"/api/albums/{album['id']}/assets", json={"media_ids": [visible.id]}
        )
        # Directly insert a trashed asset into membership to simulate an asset
        # trashed AFTER being added.
        trashed = _seed_media(db, filename="trash.jpg")
        db.add(AlbumAsset(album_id=album["id"], media_id=trashed.id, position=1))
        db.commit()
        trashed.deleted_at = datetime.now(timezone.utc)
        db.commit()

        link = _create_link(client, album["id"])
        body = client.get(f"/api/public/shared/{link['key']}").json()
        assert [i["filename"] for i in body["items"]] == ["vis.jpg"]

    def test_password_required_and_verified(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], password="secret")

        # No password → 401.
        assert client.get(f"/api/public/shared/{link['key']}").status_code == 401
        # Wrong password → 401.
        assert (
            client.get(
                f"/api/public/shared/{link['key']}", params={"password": "nope"}
            ).status_code
            == 401
        )
        # Correct password → 200.
        ok = client.get(
            f"/api/public/shared/{link['key']}", params={"password": "secret"}
        )
        assert ok.status_code == 200

    def test_expired_link_returns_404(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        link = _create_link(client, album["id"], expires_at=past)

        assert client.get(f"/api/public/shared/{link['key']}").status_code == 404

    def test_allow_download_false_strips_original_url(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], allow_download=False)

        body = client.get(f"/api/public/shared/{link['key']}").json()
        assert body["allow_download"] is False
        assert all(item["url"] is None for item in body["items"])
        # Thumbnails remain available.
        assert all(item["thumbnail_url"] for item in body["items"])

    def test_allow_download_true_includes_original_url(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], allow_download=True)

        body = client.get(f"/api/public/shared/{link['key']}").json()
        assert all(item["url"] is not None for item in body["items"])


class TestSharedLinkManagement:
    def test_list_and_revoke(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])

        assert client.get("/api/shared-links").json()["total"] == 1

        revoke = client.delete(f"/api/shared-links/{link['id']}")
        assert revoke.status_code == 200
        assert client.get("/api/shared-links").json()["total"] == 0
        # Revoked link no longer resolves publicly.
        assert client.get(f"/api/public/shared/{link['key']}").status_code == 404

    def test_patch_clears_password(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], password="secret")

        # Clear password with empty string.
        client.patch(f"/api/shared-links/{link['id']}", json={"password": ""})
        # Now accessible without a password.
        assert client.get(f"/api/public/shared/{link['key']}").status_code == 200

    def test_patch_toggles_allow_download(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], allow_download=True)

        client.patch(f"/api/shared-links/{link['id']}", json={"allow_download": False})
        body = client.get(f"/api/public/shared/{link['key']}").json()
        assert all(item["url"] is None for item in body["items"])

    def test_create_for_missing_album_404(self, client):
        assert (
            client.post("/api/shared-links", json={"album_id": 9999}).status_code == 404
        )

    def test_patch_missing_link_404(self, client):
        assert (
            client.patch(
                "/api/shared-links/9999", json={"description": "x"}
            ).status_code
            == 404
        )


class TestSharedLinkByteLayerScoping:
    """Lock in the security-review fix: media bytes are served only through
    share-scoped routes, never via leaked storage keys, and original access is
    truly gated on allow_download (not just cosmetically nulled in JSON)."""

    @pytest.fixture(autouse=True)
    def _mock_get_file(self):
        """Storage backend is not initialized in tests; return fake bytes so the
        share-scoped byte routes can be exercised."""
        with patch("find_api.routers.shared_link.get_file", return_value=b"fake-bytes"):
            yield

    def test_public_listing_does_not_leak_storage_keys(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])

        body = client.get(f"/api/public/shared/{link['key']}").json()
        item = body["items"][0]
        # Raw storage keys must never reach a public viewer.
        assert "minio_key" not in item
        assert "thumbnail_key" not in item
        # URLs point at the share-scoped routes, not /files or /api/image.
        assert item["thumbnail_url"].startswith(
            f"/api/public/shared/{link['key']}/asset/"
        )
        assert item["url"].startswith(f"/api/public/shared/{link['key']}/asset/")

    def test_thumbnail_route_serves_album_member(self, client, db):
        album, media = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])

        resp = client.get(
            f"/api/public/shared/{link['key']}/asset/{media[0].id}/thumbnail"
        )
        assert resp.status_code == 200

    def test_file_routes_reject_media_outside_album(self, client, db):
        album, _ = _make_album_with_assets(client, db, ["a.jpg"])
        outsider = _seed_media(db, filename="outside.jpg")
        link = _create_link(client, album["id"])

        # A guessed id outside the linked album must 404 at the byte layer.
        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{outsider.id}/thumbnail"
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{outsider.id}/original"
            ).status_code
            == 404
        )

    def test_original_route_blocked_when_download_disallowed(self, client, db):
        album, media = _make_album_with_assets(client, db, ["a.jpg"])
        # Give the asset a real thumbnail so the preview path is exercised
        # (distinct from the no-thumbnail case covered separately).
        media[0].thumbnail_key = "thumbnails/test/a.jpg.webp"
        media[0].thumbnail_content_type = "image/webp"
        db.commit()
        link = _create_link(client, album["id"], allow_download=False)

        # 403, not a cosmetic null — the bytes are actually withheld.
        resp = client.get(
            f"/api/public/shared/{link['key']}/asset/{media[0].id}/original"
        )
        assert resp.status_code == 403
        # Thumbnail still works (low-res preview).
        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{media[0].id}/thumbnail"
            ).status_code
            == 200
        )

    def test_thumbnail_does_not_leak_original_when_no_thumbnail_and_no_download(
        self, client, db
    ):
        """Regression for the security re-review: when an asset has no generated
        thumbnail, the thumbnail route must NOT fall back to the full-res
        original if the link forbids download."""
        album = client.post("/api/albums", json={"name": "X"}).json()
        # Asset with no thumbnail_key (helper leaves it unset).
        no_thumb = _seed_media(db, filename="nothumb.jpg")
        no_thumb.thumbnail_key = None
        db.commit()
        client.put(
            f"/api/albums/{album['id']}/assets", json={"media_ids": [no_thumb.id]}
        )
        link = _create_link(client, album["id"], allow_download=False)

        # Must refuse rather than serve the original as a "thumbnail".
        resp = client.get(
            f"/api/public/shared/{link['key']}/asset/{no_thumb.id}/thumbnail"
        )
        assert resp.status_code == 404

    def test_file_routes_enforce_password(self, client, db):
        album, media = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"], password="secret")

        # No password → 401 even on the byte routes.
        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{media[0].id}/thumbnail"
            ).status_code
            == 401
        )
        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{media[0].id}/thumbnail",
                params={"password": "secret"},
            ).status_code
            == 200
        )

    def test_file_routes_enforce_expiry(self, client, db):
        from datetime import datetime, timedelta, timezone

        album, media = _make_album_with_assets(client, db, ["a.jpg"])
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        link = _create_link(client, album["id"], expires_at=past)

        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{media[0].id}/thumbnail"
            ).status_code
            == 404
        )

    def test_revoked_link_blocks_byte_access(self, client, db):
        album, media = _make_album_with_assets(client, db, ["a.jpg"])
        link = _create_link(client, album["id"])
        client.delete(f"/api/shared-links/{link['id']}")

        assert (
            client.get(
                f"/api/public/shared/{link['key']}/asset/{media[0].id}/original"
            ).status_code
            == 404
        )
