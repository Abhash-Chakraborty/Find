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
    is_archived=False,
    deleted_at=None,
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
        width=800,
        height=600,
        thumbnail_key=f"thumbnails/test/{filename}.webp",
        thumbnail_content_type="image/webp",
        thumbnail_size=512,
        thumbnail_width=256,
        thumbnail_height=192,
        metadata_json=metadata_json,
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

    def test_hidden_media_excluded_from_gallery_listing(self, client, db):
        visible = _seed(db, filename="visible.jpg", status="indexed")
        hidden = _seed(db, filename="hidden.jpg", status="indexed", is_hidden=True)

        body = client.get("/api/gallery").json()
        ids = [item["id"] for item in body["items"]]

        assert visible.id in ids
        assert hidden.id not in ids

    def test_hidden_media_not_available_on_public_media_routes(self, client, db):
        hidden = _seed(
            db, filename="hidden-detail.jpg", status="indexed", is_hidden=True
        )

        detail_response = client.get(f"/api/image/{hidden.id}")
        thumbnail_response = client.get(
            f"/api/image/{hidden.id}/thumbnail", follow_redirects=False
        )
        like_response = client.post(f"/api/image/{hidden.id}/like")
        reprocess_response = client.post(f"/api/image/{hidden.id}/reprocess")

        assert detail_response.status_code == 404
        assert thumbnail_response.status_code == 404
        assert like_response.status_code == 404
        assert reprocess_response.status_code == 404


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


class TestGalleryDateFiltering:
    """Date-based filtering and sorting."""

    def test_sort_by_newest_default(self, client, db):
        """Gallery sorts by newest first by default."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        old = _seed(db, filename="old.jpg", status="indexed")
        old.created_at = now - timedelta(days=10)
        db.commit()

        new = _seed(db, filename="new.jpg", status="indexed")
        new.created_at = now
        db.commit()

        body = client.get("/api/gallery").json()
        assert len(body["items"]) == 2
        assert body["items"][0]["id"] == new.id
        assert body["items"][1]["id"] == old.id

    def test_sort_by_oldest(self, client, db):
        """Gallery can sort by oldest first."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        old = _seed(db, filename="old.jpg", status="indexed")
        old.created_at = now - timedelta(days=10)
        db.commit()

        new = _seed(db, filename="new.jpg", status="indexed")
        new.created_at = now
        db.commit()

        body = client.get("/api/gallery", params={"sort_order": "oldest"}).json()
        assert len(body["items"]) == 2
        assert body["items"][0]["id"] == old.id
        assert body["items"][1]["id"] == new.id

    def test_filter_by_last_30_days(self, client, db):
        """Filter shows only images from last 30 days."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        # Create images at different times
        within_30 = _seed(db, filename="recent.jpg", status="indexed")
        within_30.created_at = now - timedelta(days=5)
        db.commit()

        outside_30 = _seed(db, filename="old.jpg", status="indexed")
        outside_30.created_at = now - timedelta(days=60)
        db.commit()

        body = client.get("/api/gallery", params={"date_range": "last_30_days"}).json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == within_30.id

    def test_filter_by_last_60_days(self, client, db):
        """Filter shows only images from last 60 days."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        within_60 = _seed(db, filename="recent.jpg", status="indexed")
        within_60.created_at = now - timedelta(days=30)
        db.commit()

        outside_60 = _seed(db, filename="old.jpg", status="indexed")
        outside_60.created_at = now - timedelta(days=90)
        db.commit()

        body = client.get("/api/gallery", params={"date_range": "last_60_days"}).json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == within_60.id

    def test_filter_by_last_90_days(self, client, db):
        """Filter shows only images from last 90 days."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        within_90 = _seed(db, filename="recent.jpg", status="indexed")
        within_90.created_at = now - timedelta(days=45)
        db.commit()

        outside_90 = _seed(db, filename="old.jpg", status="indexed")
        outside_90.created_at = now - timedelta(days=120)
        db.commit()

        body = client.get("/api/gallery", params={"date_range": "last_90_days"}).json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == within_90.id

    def test_filter_by_custom_date_range(self, client, db):
        """Filter by custom date range using ISO 8601 dates."""
        # Seed images with specific dates
        before = _seed(db, filename="before.jpg", status="indexed")
        before.created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        db.commit()

        within = _seed(db, filename="within.jpg", status="indexed")
        within.created_at = datetime(2025, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
        db.commit()

        after = _seed(db, filename="after.jpg", status="indexed")
        after.created_at = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        db.commit()

        body = client.get(
            "/api/gallery",
            params={
                "date_range": "custom",
                "date_start": "2025-05-01",
                "date_end": "2025-05-31",
            },
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == within.id

    def test_custom_date_range_start_only(self, client, db):
        """Custom date range with only start date."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        before = _seed(db, filename="before.jpg", status="indexed")
        before.created_at = now - timedelta(days=30)
        db.commit()

        after = _seed(db, filename="after.jpg", status="indexed")
        after.created_at = now - timedelta(days=5)
        db.commit()

        body = client.get(
            "/api/gallery",
            params={
                "date_range": "custom",
                "date_start": (now - timedelta(days=10)).strftime("%Y-%m-%d"),
            },
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == after.id

    def test_custom_date_range_end_only(self, client, db):
        """Custom date range with only end date."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        before = _seed(db, filename="before.jpg", status="indexed")
        before.created_at = now - timedelta(days=30)
        db.commit()

        after = _seed(db, filename="after.jpg", status="indexed")
        after.created_at = now - timedelta(days=5)
        db.commit()

        body = client.get(
            "/api/gallery",
            params={
                "date_range": "custom",
                "date_end": (now - timedelta(days=10)).strftime("%Y-%m-%d"),
            },
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == before.id

    def test_date_filter_works_with_status_filter(self, client, db):
        """Date filters work together with status filters."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        # Create indexed image within last 30 days
        indexed_recent = _seed(db, filename="indexed_recent.jpg", status="indexed")
        indexed_recent.created_at = now - timedelta(days=5)
        db.commit()

        # Create indexed image outside 30 days
        indexed_old = _seed(db, filename="indexed_old.jpg", status="indexed")
        indexed_old.created_at = now - timedelta(days=60)
        db.commit()

        # Create processing image within last 30 days
        processing_recent = _seed(db, filename="proc_recent.jpg", status="processing")
        processing_recent.created_at = now - timedelta(days=5)
        db.commit()

        body = client.get(
            "/api/gallery",
            params={
                "status": "indexed",
                "date_range": "last_30_days",
            },
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == indexed_recent.id

    def test_date_filter_works_with_liked_filter(self, client, db):
        """Date filters work together with liked filters."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        liked_recent = _seed(
            db, filename="liked_recent.jpg", status="indexed", liked=True
        )
        liked_recent.created_at = now - timedelta(days=5)
        db.commit()

        liked_old = _seed(db, filename="liked_old.jpg", status="indexed", liked=True)
        liked_old.created_at = now - timedelta(days=60)
        db.commit()

        liked_notliked = _seed(
            db, filename="not_liked.jpg", status="indexed", liked=False
        )
        liked_notliked.created_at = now - timedelta(days=5)
        db.commit()

        body = client.get(
            "/api/gallery",
            params={
                "liked": True,
                "date_range": "last_30_days",
            },
        ).json()

        assert body["total"] == 1
        assert body["items"][0]["id"] == liked_recent.id

    def test_invalid_custom_dates_are_rejected(self, client, db):
        """Invalid custom dates return a validation error."""
        _seed(db, filename="valid.jpg", status="indexed")

        response = client.get(
            "/api/gallery",
            params={
                "date_range": "custom",
                "date_start": "not-a-date",
                "date_end": "2025-12-99",
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"] == "Invalid date_start. Use YYYY-MM-DD."

    def test_date_range_none_returns_all(self, client, db):
        """No date range parameter returns all items."""
        _seed(db, filename="a.jpg", status="indexed")
        _seed(db, filename="b.jpg", status="indexed")

        body = client.get("/api/gallery").json()
        assert body["total"] == 2


class TestGalleryMetadataFilters:
    """Gallery filters using EXIF and image metadata."""

    def test_gallery_filters_by_camera_make(self, client, db):
        canon = _seed(db, filename="canon.jpg", status="indexed")
        nikon = _seed(db, filename="nikon.jpg", status="indexed")
        canon.exif_json = {"make": "Canon", "model": "EOS 80D"}
        nikon.exif_json = {"make": "Nikon", "model": "D3500"}
        db.commit()

        response = client.get("/api/gallery", params={"camera_make": "Canon"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "canon.jpg"

    def test_gallery_filters_by_camera_model(self, client, db):
        canon = _seed(db, filename="canon.jpg", status="indexed")
        sony = _seed(db, filename="sony.jpg", status="indexed")
        canon.exif_json = {"make": "Canon", "model": "EOS 80D"}
        sony.exif_json = {"make": "Sony", "model": "Alpha 7"}
        db.commit()

        response = client.get("/api/gallery", params={"camera_model": "Alpha"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "sony.jpg"

    def test_gallery_filters_by_min_dimensions(self, client, db):
        small = _seed(db, filename="small.jpg", status="indexed")
        large = _seed(db, filename="large.jpg", status="indexed")
        small.width = 640
        small.height = 480
        large.width = 3000
        large.height = 2000
        db.commit()

        response = client.get(
            "/api/gallery",
            params={"min_width": 1000, "min_height": 1000},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "large.jpg"

    def test_gallery_filters_by_file_type(self, client, db):
        jpg = _seed(db, filename="photo.jpg", status="indexed")
        png = _seed(db, filename="graphic.png", status="indexed")
        jpg.content_type = "image/jpeg"
        png.content_type = "image/png"
        db.commit()

        response = client.get("/api/gallery", params={"file_type": "png"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "graphic.png"

    def test_gallery_filters_by_date_range(self, client, db):
        older = _seed(db, filename="older.jpg", status="indexed")
        newer = _seed(db, filename="newer.jpg", status="indexed")
        older.created_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
        newer.created_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        db.commit()

        response = client.get(
            "/api/gallery",
            params={"date_from": "2026-02-01", "date_to": "2026-02-28"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "newer.jpg"

    def test_gallery_date_to_includes_entire_date_only_day(self, client, db):
        early = _seed(db, filename="early.jpg", status="indexed")
        late = _seed(db, filename="late.jpg", status="indexed")
        next_day = _seed(db, filename="next-day.jpg", status="indexed")
        early.created_at = datetime(2026, 2, 28, 0, 5, tzinfo=timezone.utc)
        late.created_at = datetime(2026, 2, 28, 23, 55, tzinfo=timezone.utc)
        next_day.created_at = datetime(2026, 3, 1, 0, 1, tzinfo=timezone.utc)
        db.commit()

        response = client.get("/api/gallery", params={"date_to": "2026-02-28"})

        assert response.status_code == 200
        filenames = {item["filename"] for item in response.json()["items"]}
        assert filenames == {"early.jpg", "late.jpg"}

    def test_gallery_filters_by_orientation(self, client, db):
        landscape = _seed(db, filename="landscape.jpg", status="indexed")
        portrait = _seed(db, filename="portrait.jpg", status="indexed")
        square = _seed(db, filename="square.jpg", status="indexed")
        landscape.width = 1600
        landscape.height = 900
        portrait.width = 900
        portrait.height = 1600
        square.width = 1200
        square.height = 1200
        db.commit()

        response = client.get("/api/gallery", params={"orientation": "portrait"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "portrait.jpg"

    def test_gallery_rejects_invalid_metadata_filter_values(self, client):
        invalid_date = client.get("/api/gallery", params={"date_from": "not-a-date"})
        invalid_range = client.get(
            "/api/gallery",
            params={"date_from": "2026-03-01", "date_to": "2026-02-01"},
        )
        invalid_orientation = client.get(
            "/api/gallery",
            params={"orientation": "diagonal"},
        )

        assert invalid_date.status_code == 422
        assert invalid_range.status_code == 422
        assert invalid_orientation.status_code == 422

    def test_gallery_filter_excludes_missing_exif_data(self, client, db):
        with_exif = _seed(db, filename="canon.jpg", status="indexed")
        without_exif = _seed(db, filename="no-exif.jpg", status="indexed")
        with_exif.exif_json = {"make": "Canon", "model": "EOS 80D"}
        without_exif.exif_json = None
        db.commit()

        response = client.get("/api/gallery", params={"camera_make": "Canon"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "canon.jpg"

    def test_gallery_supports_combined_metadata_filters(self, client, db):
        large_canon = _seed(db, filename="large-canon.jpg", status="indexed")
        small_canon = _seed(db, filename="small-canon.jpg", status="indexed")
        large_sony = _seed(db, filename="large-sony.jpg", status="indexed")

        large_canon.exif_json = {"make": "Canon", "model": "EOS 80D"}
        large_canon.width = 3000
        large_canon.height = 2000

        small_canon.exif_json = {"make": "Canon", "model": "EOS M50"}
        small_canon.width = 640
        small_canon.height = 480

        large_sony.exif_json = {"make": "Sony", "model": "Alpha 7"}
        large_sony.width = 3000
        large_sony.height = 2000

        db.commit()

        response = client.get(
            "/api/gallery",
            params={"camera_make": "Canon", "min_width": 1000},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["filename"] == "large-canon.jpg"


class TestAssetStateScoping:
    """Archive + soft-delete (trash) scoping on browse surfaces.

    Asset-state columns (is_archived, deleted_at) were added in Phase 4.1.
    The rule: an asset is in the main timeline/search iff NOT hidden AND
    NOT archived AND deleted_at IS NULL. Archive/trash views (added later)
    surface those assets explicitly; single-item lookups still work so a
    detail view can open them.
    """

    def test_archived_excluded_from_gallery(self, client, db):
        _seed(db, filename="visible.jpg", status="indexed")
        _seed(db, filename="archived.jpg", status="indexed", is_archived=True)

        body = client.get("/api/gallery").json()

        assert body["total"] == 1
        assert [item["filename"] for item in body["items"]] == ["visible.jpg"]

    def test_trashed_excluded_from_gallery(self, client, db):
        _seed(db, filename="visible.jpg", status="indexed")
        _seed(
            db,
            filename="trashed.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )

        body = client.get("/api/gallery").json()

        assert body["total"] == 1
        assert [item["filename"] for item in body["items"]] == ["visible.jpg"]

    def test_archived_and_trashed_excluded_from_counts(self, client, db):
        _seed(db, filename="a.jpg", status="indexed")
        _seed(db, filename="b.jpg", status="indexed")
        _seed(db, filename="arch.jpg", status="indexed", is_archived=True)
        _seed(
            db,
            filename="trash.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )

        body = client.get("/api/gallery/counts").json()

        assert body["all"] == 2
        assert body["indexed"] == 2

    def test_archived_item_detail_still_accessible(self, client, db):
        """Archive view must be able to open an archived asset's detail."""
        archived = _seed(
            db, filename="archived.jpg", status="indexed", is_archived=True
        )

        response = client.get(f"/api/image/{archived.id}")

        assert response.status_code == 200
        assert response.json()["id"] == archived.id

    def test_liked_filter_still_excludes_archived(self, client, db):
        _seed(db, filename="liked-visible.jpg", status="indexed", liked=True)
        _seed(
            db,
            filename="liked-archived.jpg",
            status="indexed",
            liked=True,
            is_archived=True,
        )

        body = client.get("/api/gallery", params={"liked": "true"}).json()

        assert body["total"] == 1
        assert body["items"][0]["filename"] == "liked-visible.jpg"

    def test_columns_default_to_visible(self, client, db):
        """New rows default to not-archived / not-trashed (behavior-neutral)."""
        media = _seed(db, filename="default.jpg", status="indexed")

        assert media.is_archived is False
        assert media.deleted_at is None

        body = client.get("/api/gallery").json()
        assert body["total"] == 1


class TestArchiveTrashRestore:
    """Archive / trash (soft-delete) / restore endpoints (Phase 4.4)."""

    # --- archive -----------------------------------------------------------
    def test_archive_sets_flag_and_hides_from_gallery(self, client, db):
        media = _seed(db, filename="arch.jpg", status="indexed")

        response = client.post(f"/api/image/{media.id}/archive", json={})

        assert response.status_code == 200
        assert response.json() == {"id": media.id, "is_archived": True}
        assert client.get("/api/gallery").json()["total"] == 0

    def test_unarchive_returns_to_gallery(self, client, db):
        media = _seed(db, filename="arch.jpg", status="indexed", is_archived=True)
        assert client.get("/api/gallery").json()["total"] == 0

        response = client.post(
            f"/api/image/{media.id}/archive", json={"archived": False}
        )

        assert response.status_code == 200
        assert response.json()["is_archived"] is False
        assert client.get("/api/gallery").json()["total"] == 1

    def test_archive_not_found_returns_404(self, client):
        assert client.post("/api/image/99999/archive", json={}).status_code == 404

    def test_cannot_archive_trashed_image(self, client, db):
        media = _seed(
            db,
            filename="trash.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )

        response = client.post(f"/api/image/{media.id}/archive", json={})

        assert response.status_code == 409

    # --- trash / restore ---------------------------------------------------
    def test_trash_sets_deleted_at_and_hides_from_gallery(self, client, db):
        media = _seed(db, filename="t.jpg", status="indexed")

        response = client.post(f"/api/image/{media.id}/trash")

        assert response.status_code == 200
        assert response.json()["deleted_at"] is not None
        assert client.get("/api/gallery").json()["total"] == 0
        # Row + file are kept (soft delete).
        db.expire_all()
        assert db.query(Media).filter(Media.id == media.id).first() is not None

    def test_trash_does_not_delete_file(self, client, db):
        media = _seed(db, filename="t.jpg", status="indexed")

        with patch("find_api.routers.gallery.delete_file") as mock_delete:
            client.post(f"/api/image/{media.id}/trash")

        mock_delete.assert_not_called()

    def test_restore_returns_to_gallery(self, client, db):
        media = _seed(
            db,
            filename="t.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )
        assert client.get("/api/gallery").json()["total"] == 0

        response = client.post(f"/api/image/{media.id}/restore")

        assert response.status_code == 200
        assert response.json() == {"id": media.id, "deleted_at": None}
        assert client.get("/api/gallery").json()["total"] == 1

    def test_trash_is_idempotent(self, client, db):
        media = _seed(db, filename="t.jpg", status="indexed")

        first = client.post(f"/api/image/{media.id}/trash").json()["deleted_at"]
        second = client.post(f"/api/image/{media.id}/trash").json()["deleted_at"]

        assert first == second  # second trash does not bump the timestamp

    # --- list views --------------------------------------------------------
    def test_archive_view_lists_only_archived(self, client, db):
        _seed(db, filename="normal.jpg", status="indexed")
        _seed(db, filename="arch.jpg", status="indexed", is_archived=True)
        _seed(
            db,
            filename="trash.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )

        body = client.get("/api/archive").json()

        assert body["total"] == 1
        assert body["items"][0]["filename"] == "arch.jpg"
        assert body["items"][0]["is_archived"] is True

    def test_trash_view_lists_only_trashed(self, client, db):
        _seed(db, filename="normal.jpg", status="indexed")
        _seed(db, filename="arch.jpg", status="indexed", is_archived=True)
        _seed(
            db,
            filename="trash.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )

        body = client.get("/api/trash").json()

        assert body["total"] == 1
        assert body["items"][0]["filename"] == "trash.jpg"
        assert body["items"][0]["deleted_at"] is not None

    # --- empty trash -------------------------------------------------------
    def test_empty_trash_permanently_deletes_only_trashed(self, client, db):
        keep = _seed(db, filename="keep.jpg", status="indexed")
        trashed = _seed(
            db,
            filename="gone.jpg",
            status="indexed",
            deleted_at=datetime.now(timezone.utc),
        )
        keep_id, trashed_id, trashed_key = keep.id, trashed.id, trashed.minio_key

        with patch("find_api.routers.gallery.delete_file") as mock_delete:
            response = client.post("/api/trash/empty")

        assert response.status_code == 200
        body = response.json()
        assert body["deleted_count"] == 1
        assert body["deleted_ids"] == [trashed_id]
        mock_delete.assert_any_call(trashed_key)

        assert db.query(Media).filter(Media.id == trashed_id).first() is None
        assert db.query(Media).filter(Media.id == keep_id).first() is not None

    def test_empty_trash_noop_when_empty(self, client, db):
        _seed(db, filename="keep.jpg", status="indexed")

        response = client.post("/api/trash/empty")

        assert response.status_code == 200
        assert response.json()["deleted_count"] == 0
