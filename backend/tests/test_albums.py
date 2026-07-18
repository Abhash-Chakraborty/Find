"""Integration tests for album endpoints (Phase 4.2)."""

import hashlib
from datetime import datetime, timezone

from find_api.models.album import Album, AlbumAsset
from find_api.models.media import Media


def _seed_media(
    db,
    *,
    filename,
    status="indexed",
    is_archived=False,
    deleted_at=None,
    is_hidden=False,
):
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        width=800,
        height=600,
        is_hidden=is_hidden,
        is_archived=is_archived,
        deleted_at=deleted_at,
        vault_state="hidden_encrypted" if is_hidden else "visible",
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _create_album(client, name="My Album"):
    response = client.post("/api/albums", json={"name": name})
    assert response.status_code == 200
    return response.json()


class TestAlbumCrud:
    def test_create_and_list(self, client):
        created = _create_album(client, name="Trip")
        assert created["name"] == "Trip"
        assert created["asset_count"] == 0

        body = client.get("/api/albums").json()
        assert body["total"] == 1
        assert body["albums"][0]["name"] == "Trip"

    def test_get_album(self, client):
        created = _create_album(client)
        body = client.get(f"/api/albums/{created['id']}").json()
        assert body["id"] == created["id"]

    def test_get_missing_album_404(self, client):
        assert client.get("/api/albums/9999").status_code == 404

    def test_update_metadata(self, client):
        created = _create_album(client)
        response = client.patch(
            f"/api/albums/{created['id']}",
            json={"name": "Renamed", "description": "desc"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        assert body["description"] == "desc"

    def test_delete_album(self, client, db):
        created = _create_album(client)
        response = client.delete(f"/api/albums/{created['id']}")
        assert response.status_code == 200
        assert db.query(Album).filter(Album.id == created["id"]).first() is None

    def test_delete_cascades_membership(self, client, db):
        created = _create_album(client)
        media = _seed_media(db, filename="a.jpg")
        client.put(
            f"/api/albums/{created['id']}/assets", json={"media_ids": [media.id]}
        )
        assert db.query(AlbumAsset).count() == 1

        client.delete(f"/api/albums/{created['id']}")
        assert db.query(AlbumAsset).count() == 0


class TestAlbumMembership:
    def test_add_and_list_assets(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        b = _seed_media(db, filename="b.jpg")

        response = client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id, b.id]},
        )
        assert response.status_code == 200
        assert response.json()["added_count"] == 2

        body = client.get(f"/api/albums/{album['id']}/assets").json()
        assert body["total"] == 2
        assert [item["id"] for item in body["items"]] == [a.id, b.id]

    def test_add_is_idempotent_and_skips_dupes(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")

        client.put(f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id]})
        response = client.put(
            f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id]}
        )

        body = response.json()
        assert body["added_count"] == 0
        assert a.id in body["skipped_ids"]
        assert client.get(f"/api/albums/{album['id']}/assets").json()["total"] == 1

    def test_add_skips_nonexistent_media(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")

        response = client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id, 99999]},
        )
        body = response.json()
        assert body["added_ids"] == [a.id]
        assert 99999 in body["skipped_ids"]

    def test_archived_trashed_media_excluded_from_album_view(self, client, db):
        album = _create_album(client)
        visible = _seed_media(db, filename="vis.jpg")
        archived = _seed_media(db, filename="arch.jpg", is_archived=True)

        # Archived media cannot even be added (not browsable).
        add = client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [visible.id, archived.id]},
        ).json()
        assert add["added_ids"] == [visible.id]

        body = client.get(f"/api/albums/{album['id']}/assets").json()
        assert [item["id"] for item in body["items"]] == [visible.id]

    def test_asset_count_matches_listing_after_archive(self, client, db):
        """The card's asset_count must track the listing — archiving a member
        decrements it (regression: count once counted all rows)."""
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        b = _seed_media(db, filename="b.jpg")
        client.put(
            f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id, b.id]}
        )
        assert client.get(f"/api/albums/{album['id']}").json()["asset_count"] == 2

        # Archive one member directly.
        a.is_archived = True
        db.commit()

        # Both the listing and the count drop to 1 — they agree.
        listing = client.get(f"/api/albums/{album['id']}/assets").json()
        assert listing["total"] == 1
        assert client.get(f"/api/albums/{album['id']}").json()["asset_count"] == 1
        # And it shows in the albums list card too.
        card = next(
            alb
            for alb in client.get("/api/albums").json()["albums"]
            if alb["id"] == album["id"]
        )
        assert card["asset_count"] == 1

    def test_remove_assets(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        b = _seed_media(db, filename="b.jpg")
        client.put(
            f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id, b.id]}
        )

        response = client.request(
            "DELETE",
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id]},
        )
        assert response.status_code == 200
        assert response.json()["removed_ids"] == [a.id]

        body = client.get(f"/api/albums/{album['id']}/assets").json()
        assert [item["id"] for item in body["items"]] == [b.id]


class TestAlbumCover:
    def test_set_cover_must_be_member(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")

        # Not a member yet → rejected.
        rejected = client.patch(
            f"/api/albums/{album['id']}", json={"cover_media_id": a.id}
        )
        assert rejected.status_code == 400

        client.put(f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id]})
        ok = client.patch(f"/api/albums/{album['id']}", json={"cover_media_id": a.id})
        assert ok.status_code == 200
        assert ok.json()["cover_media_id"] == a.id
        assert ok.json()["cover_thumbnail_url"] == f"/api/image/{a.id}/thumbnail"

    def test_cover_cleared_when_member_removed(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        client.put(f"/api/albums/{album['id']}/assets", json={"media_ids": [a.id]})
        client.patch(f"/api/albums/{album['id']}", json={"cover_media_id": a.id})

        client.request(
            "DELETE",
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id]},
        )
        body = client.get(f"/api/albums/{album['id']}").json()
        assert body["cover_media_id"] is None


class TestAlbumOrdering:
    def test_reorder_sets_position(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        b = _seed_media(db, filename="b.jpg")
        c = _seed_media(db, filename="c.jpg")
        client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id, b.id, c.id]},
        )

        # Reverse the order.
        response = client.put(
            f"/api/albums/{album['id']}/order",
            json={"media_ids": [c.id, b.id, a.id]},
        )
        assert response.status_code == 200

        body = client.get(f"/api/albums/{album['id']}/assets").json()
        assert [item["id"] for item in body["items"]] == [c.id, b.id, a.id]

    def test_reorder_partial_appends_leftovers(self, client, db):
        album = _create_album(client)
        a = _seed_media(db, filename="a.jpg")
        b = _seed_media(db, filename="b.jpg")
        c = _seed_media(db, filename="c.jpg")
        client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id, b.id, c.id]},
        )

        # Only specify c first; a and b keep relative order after it.
        client.put(f"/api/albums/{album['id']}/order", json={"media_ids": [c.id]})

        body = client.get(f"/api/albums/{album['id']}/assets").json()
        assert [item["id"] for item in body["items"]] == [c.id, a.id, b.id]
