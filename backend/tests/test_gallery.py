"""Tests for GET /api/gallery — response shape and status/liked filtering."""

import hashlib
from datetime import datetime, timezone

from find_api.models.media import Media


def _seed(db, *, filename, status, liked=False, metadata_json=None):
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
        metadata_json=metadata_json,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


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
            "liked",
            "url",
        }
        assert expected_keys.issubset(item.keys())

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
        assert "stage_status" in body["metadata"]
        assert body["metadata"]["stage_status"]["captioning"]["status"] == "failed"
        assert (
            body["metadata"]["stage_status"]["captioning"]["error"]
            == "Model loading failed"
        )


class TestGalleryFiltering:
    """Status and liked filtering."""

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
