import io
import os
import zipfile
from unittest.mock import patch

from PIL import Image
from find_api.models.media import Media


def get_valid_image_bytes():
    """Generate a 1x1 valid PNG for testing."""
    img = Image.new("RGB", (1, 1), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestUploadSuccess:
    """Successful upload response shape."""

    def test_single_image(self, client):
        response = client.post(
            "/api/upload",
            files=[("files", ("photo.png", get_valid_image_bytes(), "image/png"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert "total" in body
        assert body["total"] == 1

        result = body["results"][0]
        assert result["filename"] == "photo.png"
        assert result["status"] == "uploaded"
        assert "media_id" in result
        assert "job_id" in result

    def test_single_image_persists_analysis_job_id(self, client, db):
        response = client.post(
            "/api/upload",
            files=[("files", ("photo.png", get_valid_image_bytes(), "image/png"))],
        )

        result = response.json()["results"][0]
        media = db.query(Media).filter(Media.id == result["media_id"]).one()
        assert media.analysis_job_id == result["job_id"]

    def test_single_image_persists_thumbnail_metadata(self, client, db):
        response = client.post(
            "/api/upload",
            files=[("files", ("photo.png", get_valid_image_bytes(), "image/png"))],
        )

        result = response.json()["results"][0]
        media = db.query(Media).filter(Media.id == result["media_id"]).one()
        assert media.thumbnail_key == "thumbnails/ab/abc.webp"
        assert media.thumbnail_content_type == "image/webp"
        assert media.thumbnail_size == 128
        assert media.thumbnail_width == 1
        assert media.thumbnail_height == 1

    def test_thumbnail_failure_does_not_block_upload(self, client, db):
        with patch("find_api.routers.upload.upload_thumbnail", return_value=None):
            response = client.post(
                "/api/upload",
                files=[("files", ("photo.png", get_valid_image_bytes(), "image/png"))],
            )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "uploaded"

        media = db.query(Media).filter(Media.id == result["media_id"]).one()
        assert media.thumbnail_key is None
        assert media.minio_key is not None

    def test_duplicate_returns_duplicate_status(self, client):
        data = get_valid_image_bytes()
        first = client.post(
            "/api/upload",
            files=[("files", ("a.png", data, "image/png"))],
        )
        assert first.status_code == 200
        response = client.post(
            "/api/upload",
            files=[("files", ("a.png", data, "image/png"))],
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "duplicate"


class TestUploadInvalid:
    """Invalid upload behavior."""

    def test_non_image_rejected(self, client):
        response = client.post(
            "/api/upload",
            files=[("files", ("readme.txt", b"hello", "text/plain"))],
        )
        assert response.status_code == 400

    def test_corrupted_image_rejected(self, client):
        """Even if mime is image/png, invalid bytes should be rejected."""
        response = client.post(
            "/api/upload",
            files=[("files", ("corrupted.png", b"not-a-real-image", "image/png"))],
        )
        assert response.status_code == 400
        assert "corrupted" in response.json()["detail"].lower()

    def test_missing_files_returns_422(self, client):
        response = client.post("/api/upload")
        assert response.status_code == 422


class TestBulkUpload:
    """Bulk ZIP upload behavior."""

    def test_bulk_upload_mixed_content(self, client):
        """ZIP with some valid and some invalid images should report individual failures."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("valid.png", get_valid_image_bytes())
            zf.writestr("corrupted.jpg", b"not-an-image")
            zf.writestr("readme.txt", b"just text")

        zip_buffer.seek(0)
        response = client.post(
            "/api/upload/bulk",
            files=[
                (
                    "file",
                    ("images.zip", zip_buffer.read(), "application/zip"),
                )
            ],
        )

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 3

        # valid.png should succeed
        valid = next(r for r in results if r["filename"] == "valid.png")
        assert valid["status"] == "uploaded"

        # corrupted.jpg should fail (Pillow check)
        corrupted = next(r for r in results if r["filename"] == "corrupted.jpg")
        assert corrupted["status"] == "failed"
        assert "corrupted" in corrupted["error"].lower()

        # readme.txt should fail (MIME/extension check)
        txt = next(r for r in results if r["filename"] == "readme.txt")
        assert txt["status"] == "failed"
        assert "not an image" in txt["error"].lower()

    def test_bulk_upload_nested_zip_rejected(self, client):
        """ZIP containing another ZIP archive is rejected."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("inner.zip", b"fake zip content")
        zip_buffer.seek(0)
        response = client.post(
            "/api/upload/bulk",
            files=[("file", ("images.zip", zip_buffer.read(), "application/zip"))],
        )
        assert response.status_code == 400
        assert "nested" in response.json()["detail"].lower()

    def test_bulk_upload_uses_basename_for_windows_style_paths(self, client):
        """ZIP member paths using backslashes should store only the base filename."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(r"nested\windows-path.png", get_valid_image_bytes())
        zip_buffer.seek(0)

        response = client.post(
            "/api/upload/bulk",
            files=[("file", ("images.zip", zip_buffer.read(), "application/zip"))],
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "uploaded"
        assert result["filename"] == "windows-path.png"

    def test_bulk_upload_total_size_exceeded(self, client):
        """ZIP whose total uncompressed size exceeds limit is rejected."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("img.png", get_valid_image_bytes())
        zip_buffer.seek(0)

        with patch("find_api.routers.upload.settings.MAX_BULK_TOTAL_SIZE_MB", 0):
            response = client.post(
                "/api/upload/bulk",
                files=[("file", ("images.zip", zip_buffer.read(), "application/zip"))],
            )
        assert response.status_code == 400
        assert "uncompressed" in response.json()["detail"].lower()

    def test_bulk_upload_suspicious_ratio(self, client):
        """ZIP with suspicious compression ratio is rejected."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            # Highly compressible data (zeros) produces a high compression ratio
            zf.writestr("bomb.png", b"\x00" * 100_000)
        zip_buffer.seek(0)

        response = client.post(
            "/api/upload/bulk",
            files=[("file", ("images.zip", zip_buffer.read(), "application/zip"))],
        )
        assert response.status_code == 400
        assert "ratio" in response.json()["detail"].lower()

    def test_bulk_upload_oversized_file_skipped(self, client):
        """Individual file exceeding MAX_UPLOAD_SIZE_MB is skipped, others proceed."""
        large_data = os.urandom(2 * 1024 * 1024)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("valid.png", get_valid_image_bytes())
            zf.writestr("huge.jpg", large_data)
        zip_buffer.seek(0)

        with patch("find_api.routers.upload.settings.MAX_UPLOAD_SIZE_MB", 1):
            response = client.post(
                "/api/upload/bulk",
                files=[("file", ("images.zip", zip_buffer.read(), "application/zip"))],
            )
        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 2

        valid = next(r for r in results if r["filename"] == "valid.png")
        assert valid["status"] == "uploaded"

        huge = next(r for r in results if r["filename"] == "huge.jpg")
        assert huge["status"] == "failed"
        assert "exceeds max upload size" in huge["error"].lower()
