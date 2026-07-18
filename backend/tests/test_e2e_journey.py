"""End-to-end API journey across the whole overhaul surface (plan §10.2).

True browser E2E (Playwright) is not installed in this repo, so this is the
API-level equivalent: one test drives the entire user journey through the live
ASGI app, asserting the server-observable state at each hop. It is the honest
substitute for §10.2 until a browser E2E rig exists — it exercises the real
routers, real DB transitions, and the cross-feature seams (album → share →
public view, timeline ↔ archive/trash), which is where integration bugs hide.

Journey:
    seed library
      → timeline browse (buckets + one window)
      → create album + add assets
      → create public share link → open it UNAUTHENTICATED → verify scoping
      → password-protected share: refused without password, served with it
      → favorite an asset
      → archive an asset (leaves timeline, appears in /archive) → unarchive
      → trash an asset (leaves timeline, appears in /trash) → restore
      → settings: hardware capability report resolves a plan

Storage bytes are mocked at the boundary (conftest mocks upload/serve for the
gallery; the share byte-routes are exercised only where they short-circuit
before touching storage, e.g. the download-disallowed 403 gate).
"""

import hashlib
from datetime import datetime, timezone

import pytest

from find_api.models.media import Media


def _seed(db, filename, *, liked=False):
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/e2e/{filename}",
        thumbnail_key=f"thumbnails/e2e/{filename}.webp",
        thumbnail_content_type="image/webp",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=1600,
        height=1200,
        liked=liked,
        is_hidden=False,
        is_archived=False,
        deleted_at=None,
        vault_state="visible",
        created_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


class TestFullJourney:
    def test_browse_album_share_state_transitions(self, client, db):
        # --- seed a small library ------------------------------------------
        a = _seed(db, "alpha.jpg")
        b = _seed(db, "bravo.jpg")
        c = _seed(db, "charlie.jpg")

        # --- timeline browse ------------------------------------------------
        buckets = client.get("/api/timeline/buckets").json()
        assert buckets["total"] == 3
        assert buckets["buckets"][0]["timeBucket"] == "2025-06-01"

        window = client.get("/api/timeline/bucket?timeBucket=2025-06").json()
        assert window["count"] == 3
        assert set(window["id"]) == {a.id, b.id, c.id}
        # ratio drives the justified layout: 1600/1200 = 1.3333
        assert window["ratio"][0] == pytest.approx(1.3333, abs=1e-3)

        # --- album: create + add members -----------------------------------
        album = client.post("/api/albums", json={"name": "Trip"}).json()
        added = client.put(
            f"/api/albums/{album['id']}/assets",
            json={"media_ids": [a.id, b.id, c.id]},
        ).json()
        assert added["added_count"] == 3
        assert client.get(f"/api/albums/{album['id']}").json()["asset_count"] == 3

        # --- share link: open UNAUTHENTICATED, verify scoping --------------
        created = client.post(
            "/api/shared-links",
            json={"album_id": album["id"], "allow_download": False},
        ).json()
        key = created["key"]  # raw key returned exactly once
        assert created["url"] == f"/api/public/shared/{key}"

        public = client.get(f"/api/public/shared/{key}").json()
        assert public["album"]["name"] == "Trip"
        assert public["total"] == 3
        assert public["allow_download"] is False
        # Public items expose ONLY share-scoped URLs — never raw storage keys.
        for item in public["items"]:
            assert "minio_key" not in item
            assert "thumbnail_key" not in item
            assert item["thumbnail_url"].startswith(f"/api/public/shared/{key}/asset/")
            # Download disallowed → no original URL offered.
            assert item["url"] is None

        # Download is gated server-side, not just in the URL list: the original
        # byte route refuses with 403 before ever touching storage.
        denied = client.get(f"/api/public/shared/{key}/asset/{a.id}/original")
        assert denied.status_code == 403

        # An unknown key is indistinguishable from an expired one (404, no leak).
        assert client.get("/api/public/shared/deadbeef").status_code == 404

        # --- password-protected share -------------------------------------
        locked = client.post(
            "/api/shared-links",
            json={"album_id": album["id"], "password": "s3cret"},
        ).json()
        lkey = locked["key"]
        # No password → 401.
        assert client.get(f"/api/public/shared/{lkey}").status_code == 401
        # Wrong password → 401.
        assert client.get(f"/api/public/shared/{lkey}?password=nope").status_code == 401
        # Correct password → 200.
        unlocked = client.get(f"/api/public/shared/{lkey}?password=s3cret")
        assert unlocked.status_code == 200
        assert unlocked.json()["total"] == 3

        # --- favorite ------------------------------------------------------
        liked = client.post(f"/api/image/{a.id}/like").json()
        assert liked["liked"] is True
        assert client.get("/api/timeline/buckets?liked=true").json()["total"] == 1

        # --- archive: leaves timeline, appears in /archive, then back ------
        archived = client.post(
            f"/api/image/{b.id}/archive", json={"archived": True}
        ).json()
        assert archived["is_archived"] is True
        assert client.get("/api/timeline/buckets").json()["total"] == 2
        arch_list = client.get("/api/archive").json()
        assert arch_list["total"] == 1
        assert arch_list["items"][0]["id"] == b.id
        # Archived asset is also excluded from the album view (browsable scope).
        assert client.get(f"/api/albums/{album['id']}/assets").json()["total"] == 2

        # Unarchive → back in the timeline.
        client.post(f"/api/image/{b.id}/archive", json={"archived": False})
        assert client.get("/api/timeline/buckets").json()["total"] == 3

        # --- trash: leaves timeline, appears in /trash, then restore -------
        trashed = client.post(f"/api/image/{c.id}/trash").json()
        assert trashed["deleted_at"] is not None
        assert client.get("/api/timeline/buckets").json()["total"] == 2
        trash_list = client.get("/api/trash").json()
        assert trash_list["total"] == 1
        assert trash_list["items"][0]["id"] == c.id

        # A trashed asset cannot be archived — must restore first (409).
        assert (
            client.post(
                f"/api/image/{c.id}/archive", json={"archived": True}
            ).status_code
            == 409
        )

        restored = client.post(f"/api/image/{c.id}/restore").json()
        assert restored["deleted_at"] is None
        assert client.get("/api/timeline/buckets").json()["total"] == 3

        # --- settings: hardware report resolves a plan ---------------------
        hw = client.get("/api/config/hardware").json()
        assert hw["accel_mode"] in {"auto", "gpu", "cpu"}
        assert "capabilities" in hw
        # A plan always resolves with CPU as the guaranteed terminal fallback.
        resolved = hw["resolved"]
        assert resolved  # non-empty plan
