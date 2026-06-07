"""Tests for gallery endpoints — list/detail/delete and related behavior."""

import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

from find_api.models.cluster import Cluster
from find_api.models.media import Media


def _seed(
    db,
    *,
    filename,
    status,
    liked=False,
    metadata_json=None,
    is_hidden=False,
):
    """Insert a Media row into the test database."""
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        liked=liked,
        is_hidden=is_hidden,
        width=800,
        height=600,
        thumbnail_key=f"thumbnails/test/{filename}.webp",
        thumbnail_content_type="image/webp",
        thumbnail_size=512,
        thumbnail_width=256,
        thumbnail_height=192,
        metadata_json=metadata_json,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _seed_cluster(db, *, member_ids: list[int]) -> Cluster:
    cluster = Cluster(
        cluster_type="general",
        member_ids=member_ids,
        member_count=len(member_ids),
        label="Test cluster",
        description="Cluster used in tests",
        created_at=datetime.now(timezone.utc),
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    return cluster


class TestGalleryResponseShape:
    """Gallery response shape."""

    def test_empty_gallery(self, client):
        response = client.get("/api/gallery")

        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert "skip" in body
        assert "limit" in body
        assert "page" in body

    def test_item_keys(self, client, db):
        _seed(db, filename="sunset.jpg", status="indexed")

        response = client.get("/api/gallery")
        item = response.json()["items"][0]

        expected_keys = {
            "id",
            "filename",
            "status",
            "created_at",
            "processed_at",
            "width",
            "height",
            "file_size",
            "cluster_id",
            "minio_key",
            "thumbnail_key",
            "thumbnail_content_type",
            "thumbnail_size",
            "thumbnail_width",
            "thumbnail_height",
            "thumbnail_url",
            "liked",
            "url",
            "thumbnail_url",
        }
        assert expected_keys.issubset(item.keys())
        assert item["thumbnail_url"] == f"/api/image/{item['id']}/thumbnail"

    def test_thumbnail_redirect_prefers_thumbnail_key(self, client, db):
        media = _seed(db, filename="sunset.jpg", status="indexed")

        with patch(
            "find_api.routers.gallery.get_file_url",
            side_effect=lambda key: f"http://fake/{key}",
        ):
            response = client.get(
                f"/api/image/{media.id}/thumbnail", follow_redirects=False
            )

        assert response.status_code == 307
        assert (
            response.headers["location"]
            == "http://fake/thumbnails/test/sunset.jpg.webp"
        )

    def test_thumbnail_redirect_falls_back_to_original(self, client, db):
        media = _seed(db, filename="legacy.jpg", status="indexed")
        media.thumbnail_key = None
        db.commit()

        with patch(
            "find_api.routers.gallery.get_file_url",
            side_effect=lambda key: f"http://fake/{key}",
        ):
            response = client.get(
                f"/api/image/{media.id}/thumbnail", follow_redirects=False
            )

        assert response.status_code == 307
        assert response.headers["location"] == "http://fake/images/test/legacy.jpg"

    def test_backfill_missing_thumbnails_enqueues_thumbnail_only_jobs(self, client, db):
        existing = _seed(db, filename="existing.jpg", status="indexed")
        missing_a = _seed(db, filename="missing-a.jpg", status="indexed")
        missing_b = _seed(db, filename="missing-b.jpg", status="indexed")
        missing_a.thumbnail_key = None
        missing_b.thumbnail_key = None
        db.commit()

        class FakeQueue:
            def __init__(self):
                self.calls = []

            def enqueue(self, func, media_id, **kwargs):
                self.calls.append((func, media_id, kwargs))

                class FakeJob:
                    id = f"job-{media_id}"

                return FakeJob()

        queue = FakeQueue()
        with patch("find_api.routers.gallery.get_task_queue", return_value=queue):
            response = client.post("/api/thumbnails/backfill")

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 2
        assert body["remaining"] == 0
        assert set(body["job_ids"]) == {f"job-{missing_a.id}", f"job-{missing_b.id}"}
        assert {call[1] for call in queue.calls} == {missing_a.id, missing_b.id}
        assert existing.id not in {call[1] for call in queue.calls}

    def test_backfill_missing_thumbnails_respects_limit(self, client, db):
        for index in range(3):
            media = _seed(db, filename=f"missing-{index}.jpg", status="indexed")
            media.thumbnail_key = None
        db.commit()

        class FakeQueue:
            def enqueue(self, _func, media_id, **_kwargs):
                class FakeJob:
                    id = f"job-{media_id}"

                return FakeJob()

        with patch("find_api.routers.gallery.get_task_queue", return_value=FakeQueue()):
            response = client.post("/api/thumbnails/backfill?limit=2")

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 2
        assert body["remaining"] == 1

    def test_backfill_missing_thumbnails_noops_when_complete(self, client, db):
        _seed(db, filename="existing.jpg", status="indexed")

        response = client.post("/api/thumbnails/backfill")

        assert response.status_code == 200
        assert response.json() == {
            "queued": 0,
            "remaining": 0,
            "job_ids": [],
            "message": "No missing thumbnails found.",
        }

    def test_indexed_item_includes_metadata(self, client, db):
        _seed(
            db,
            filename="doc.png",
            status="indexed",
            metadata_json={
                "caption": "a sunset",
                "objects": ["sun"],
                "ocr_text": "hello",
            },
        )

        item = client.get("/api/gallery").json()["items"][0]
        assert item["caption"] == "a sunset"
        assert item["objects"] == ["sun"]
        assert item["has_text"] is True

    def test_image_detail_includes_stage_status(self, client, db):
        media = _seed(
            db,
            filename="stage_test.png",
            status="indexed",
            metadata_json={
                "caption": "sunset",
                "objects": [],
                "ocr_text": "",
                "stage_status": {
                    "object_detection": {"status": "success", "error": None},
                    "captioning": {"status": "failed", "error": "Model loading failed"},
                    "ocr": {"status": "success", "error": None},
                    "embedding": {"status": "success", "error": None},
                },
            },
        )

        response = client.get(f"/api/image/{media.id}")
        assert response.status_code == 200
        body = response.json()
        assert body["thumbnail_url"] == f"/api/image/{media.id}/thumbnail"
        assert "stage_status" in body["metadata"]
        assert body["metadata"]["stage_status"]["captioning"]["status"] == "failed"
        assert (
            body["metadata"]["stage_status"]["captioning"]["error"]
            == "Model loading failed"
        )

    def test_image_detail_includes_cluster_label(self, client, db):
        media = _seed(db, filename="clustered.jpg", status="indexed")
        cluster = _seed_cluster(db, member_ids=[media.id])
        media.cluster_id = cluster.id
        db.commit()

        response = client.get(f"/api/image/{media.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["cluster_id"] == cluster.id
        assert body["cluster_label"] == "Test cluster"


class TestGalleryFiltering:
    """Status and liked filtering."""

    def test_gallery_counts_excludes_hidden_media(self, client, db):
        _seed(db, filename="indexed.jpg", status="indexed")
        _seed(db, filename="processing.jpg", status="processing")
        _seed(db, filename="failed.jpg", status="failed")
        _seed(db, filename="pending.jpg", status="pending")
        _seed(db, filename="hidden.jpg", status="indexed", is_hidden=True)

        response = client.get("/api/gallery/counts")

        assert response.status_code == 200
        assert response.json() == {
            "all": 4,
            "indexed": 1,
            "processing": 1,
            "failed": 1,
        }

    def test_gallery_counts_respects_liked_filter(self, client, db):
        _seed(db, filename="liked-indexed.jpg", status="indexed", liked=True)
        _seed(db, filename="liked-failed.jpg", status="failed", liked=True)
        _seed(db, filename="unliked-indexed.jpg", status="indexed", liked=False)

        response = client.get("/api/gallery/counts", params={"liked": "true"})

        assert response.status_code == 200
        assert response.json() == {
            "all": 2,
            "indexed": 1,
            "processing": 0,
            "failed": 1,
        }

    def test_filter_by_status(self, client, db):
        _seed(db, filename="a.jpg", status="pending")
        _seed(db, filename="b.jpg", status="indexed")

        body = client.get("/api/gallery", params={"status": "pending"}).json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "a.jpg"

    def test_filter_by_liked(self, client, db):
        _seed(db, filename="fav.jpg", status="indexed", liked=True)
        _seed(db, filename="meh.jpg", status="indexed", liked=False)

        body = client.get("/api/gallery", params={"liked": True}).json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "fav.jpg"

    def test_pagination(self, client, db):
        for i in range(5):
            _seed(db, filename=f"img_{i}.jpg", status="indexed")

        body = client.get("/api/gallery", params={"skip": 2, "limit": 2}).json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["skip"] == 2


class TestDeleteImage:
    """DELETE /api/image/{media_id}"""

    def test_delete_success_removes_db_row_and_minio_objects(self, client, db):
        media = _seed(db, filename="delete-me.jpg", status="indexed")

        with patch("find_api.routers.gallery.delete_file") as mock_delete_file:
            response = client.delete(f"/api/image/{media.id}")

        assert response.status_code == 200
        assert response.json() == {"message": "Image deleted", "id": media.id}
        assert db.query(Media).filter(Media.id == media.id).first() is None
        mock_delete_file.assert_any_call(media.minio_key)
        mock_delete_file.assert_any_call(media.thumbnail_key)

    def test_delete_not_found_returns_404(self, client):
        response = client.delete("/api/image/99999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Image not found"

    def test_delete_updates_cluster_member_ids(self, client, db):
        first = _seed(db, filename="cluster-a.jpg", status="indexed")
        second = _seed(db, filename="cluster-b.jpg", status="indexed")
        third = _seed(db, filename="cluster-c.jpg", status="indexed")
        cluster = _seed_cluster(db, member_ids=[first.id, second.id, third.id])

        with patch("find_api.routers.gallery.delete_file"):
            response = client.delete(f"/api/image/{second.id}")

        assert response.status_code == 200
        db.refresh(cluster)
        assert cluster.member_ids == [first.id, third.id]
        assert cluster.member_count == 2
        assert db.query(Media).filter(Media.id == second.id).first() is None


class TestBulkDeleteImages:
    """POST /api/images/bulk-delete"""

    def test_bulk_delete_removes_rows_storage_and_cluster_members(self, client, db):
        first = _seed(db, filename="bulk-a.jpg", status="indexed")
        second = _seed(db, filename="bulk-b.jpg", status="indexed")
        third = _seed(db, filename="bulk-c.jpg", status="indexed")
        cluster = _seed_cluster(db, member_ids=[first.id, second.id, third.id])

        with patch("find_api.routers.gallery.delete_file") as mock_delete_file:
            response = client.post(
                "/api/images/bulk-delete",
                json={"media_ids": [first.id, second.id]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted_ids"] == [first.id, second.id]
        assert body["deleted_count"] == 2
        assert body["missing_ids"] == []
        assert body["failed_ids"] == []
        assert db.query(Media).filter(Media.id.in_([first.id, second.id])).all() == []
        db.refresh(cluster)
        assert cluster.member_ids == [third.id]
        assert cluster.member_count == 1
        mock_delete_file.assert_any_call(first.minio_key)
        mock_delete_file.assert_any_call(first.thumbnail_key)
        mock_delete_file.assert_any_call(second.minio_key)
        mock_delete_file.assert_any_call(second.thumbnail_key)

    def test_bulk_delete_reports_missing_ids_without_failing_valid_deletes(
        self, client, db
    ):
        media = _seed(db, filename="bulk-existing.jpg", status="indexed")

        with patch("find_api.routers.gallery.delete_file"):
            response = client.post(
                "/api/images/bulk-delete",
                json={"media_ids": [media.id, 99999]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted_ids"] == [media.id]
        assert body["missing_ids"] == [99999]
        assert body["failed_ids"] == []
        assert db.query(Media).filter(Media.id == media.id).first() is None

    def test_bulk_delete_reports_storage_failures_and_keeps_failed_rows(
        self, client, db
    ):
        first = _seed(db, filename="bulk-fail-a.jpg", status="indexed")
        second = _seed(db, filename="bulk-fail-b.jpg", status="indexed")

        def fail_first_delete(key: str) -> None:
            if key == first.minio_key:
                raise RuntimeError("storage unavailable")

        with patch(
            "find_api.routers.gallery.delete_file", side_effect=fail_first_delete
        ):
            response = client.post(
                "/api/images/bulk-delete",
                json={"media_ids": [first.id, second.id]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["deleted_ids"] == [second.id]
        assert body["failed_ids"] == [first.id]
        assert db.query(Media).filter(Media.id == first.id).first() is not None
        assert db.query(Media).filter(Media.id == second.id).first() is None
