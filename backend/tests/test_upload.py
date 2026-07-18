import concurrent.futures
import io
import os
import zipfile
from unittest.mock import patch

import pytest
from PIL import Image
from find_api.core.config import PILLOW_MAX_IMAGE_PIXELS, Settings
from find_api.models.media import Media
from find_api.routers.upload import _verify_image_content


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


class TestPixelLimitValidation:
    """Image pixel-limit validation (thread-safe, Pillow ceiling-aware)."""

    def test_pixel_limit_normal_image(self, client):
        """Normal image within pixel limit should succeed."""
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        response = client.post(
            "/api/upload",
            files=[("files", ("normal.png", buf.getvalue(), "image/png"))],
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "uploaded"

    def test_pixel_limit_oversized_image(self, client):
        """Image exceeding MAX_IMAGE_PIXELS should be rejected."""
        with patch("find_api.routers.upload.settings.MAX_IMAGE_PIXELS", 100):
            img = Image.new("RGB", (50, 50), color="blue")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            response = client.post(
                "/api/upload",
                files=[("files", ("oversized.png", buf.getvalue(), "image/png"))],
            )
            assert response.status_code == 400
            assert "exceeds pixel limit" in response.json()["detail"].lower()

    def test_pixel_limit_concurrent_validation(self, client):
        """Concurrent uploads should each validate independently without global mutation."""
        pillow_limit = Image.MAX_IMAGE_PIXELS

        def validate_image(size):
            img = Image.new("RGB", (size, size), color="green")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            _verify_image_content(f"image_{size}.png", buf.getvalue())
            return size

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(validate_image, size) for size in [10, 50, 100]]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert sorted(results) == [10, 50, 100]
        assert Image.MAX_IMAGE_PIXELS == pillow_limit

    def test_config_rejects_limit_above_pillow_ceiling(self):
        with pytest.raises(ValueError, match="Pillow's built-in safety ceiling"):
            Settings(MAX_IMAGE_PIXELS=PILLOW_MAX_IMAGE_PIXELS + 1)


class TestMultipartUploadLimit:
    """The multipart endpoint enforces MAX_BULK_FILES before ingestion."""

    @staticmethod
    def _files(count: int):
        data = get_valid_image_bytes()
        return [
            ("files", (f"photo-{index}.png", data, "image/png"))
            for index in range(count)
        ]

    def test_below_limit_proceeds(self, client):
        with (
            patch("find_api.routers.upload.settings.MAX_BULK_FILES", 3),
            patch(
                "find_api.routers.upload._ingest_image",
                return_value={"status": "uploaded"},
            ) as ingest,
        ):
            response = client.post("/api/upload", files=self._files(2))

        assert response.status_code == 200
        assert response.json()["total"] == 2
        assert ingest.call_count == 2

    def test_exact_limit_proceeds(self, client):
        with (
            patch("find_api.routers.upload.settings.MAX_BULK_FILES", 3),
            patch(
                "find_api.routers.upload._ingest_image",
                return_value={"status": "uploaded"},
            ) as ingest,
        ):
            response = client.post("/api/upload", files=self._files(3))

        assert response.status_code == 200
        assert response.json()["total"] == 3
        assert ingest.call_count == 3

    def test_above_limit_is_rejected_before_ingestion(self, client):
        with (
            patch("find_api.routers.upload.settings.MAX_BULK_FILES", 3),
            patch("find_api.routers.upload._ingest_image") as ingest,
        ):
            response = client.post("/api/upload", files=self._files(4))

        assert response.status_code == 413
        assert response.json()["detail"] == "Request contains more than 3 files"
        ingest.assert_not_called()


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
