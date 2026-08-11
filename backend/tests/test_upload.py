import concurrent.futures
import hashlib
import io
import os
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy.exc import IntegrityError
from find_api.core.config import PILLOW_MAX_IMAGE_PIXELS, Settings
from find_api.models.media import Media
from find_api.routers.upload import _ingest_image, _verify_image_content


def get_valid_image_bytes(color="red"):
    """Generate a 1x1 valid PNG for testing."""
    img = Image.new("RGB", (1, 1), color=color)
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


class TestUploadRace:
    """A file_hash race during insert must not poison the shared session."""

    def test_race_on_insert_is_recovered_without_poisoning_session(self, client, db):
        data = get_valid_image_bytes()
        file_hash = hashlib.sha256(data).hexdigest()

        # Row inserted by a "concurrent" request that our own existing-file
        # check below has not seen yet.
        existing = Media(
            file_hash=file_hash,
            minio_key=f"images/{file_hash[:2]}/{file_hash}.png",
            filename="first.png",
            content_type="image/png",
            file_size=len(data),
            status="pending",
        )
        db.add(existing)
        db.commit()

        real_query = db.query
        seen = False

        def query_once_empty(model):
            nonlocal seen
            if not seen:
                seen = True
                empty = MagicMock()
                empty.filter.return_value.first.return_value = None
                return empty
            return real_query(model)

        with patch.object(db, "query", side_effect=query_once_empty):
            raced = _ingest_image(
                filename="second.png",
                content_type="image/png",
                file_data=data,
                db=db,
            )

        assert raced["status"] == "duplicate"
        assert raced["media_id"] == existing.id

        # Session must still work for the next file in the same batch.
        next_result = _ingest_image(
            filename="third.png",
            content_type="image/png",
            file_data=get_valid_image_bytes(color="blue"),
            db=db,
        )
        assert next_result["status"] == "uploaded"

    def test_unrelated_integrity_error_is_not_treated_as_duplicate(self, client, db):
        data = get_valid_image_bytes(color="green")
        file_hash = hashlib.sha256(data).hexdigest()

        # A row with this exact hash already exists (e.g. inserted by an
        # unrelated concurrent request), so a naive "does a matching row
        # exist after the failure" check would misread this as that race.
        existing = Media(
            file_hash=file_hash,
            minio_key=f"images/{file_hash[:2]}/{file_hash}.png",
            filename="first.png",
            content_type="image/png",
            file_size=len(data),
            status="pending",
        )
        db.add(existing)
        db.commit()

        real_query = db.query
        seen = False

        def query_once_empty(model):
            nonlocal seen
            if not seen:
                seen = True
                empty = MagicMock()
                empty.filter.return_value.first.return_value = None
                return empty
            return real_query(model)

        def failing_commit():
            raise IntegrityError(
                "INSERT INTO media ...",
                {},
                Exception("NOT NULL constraint failed: media.uploader_user_id"),
            )

        with (
            patch.object(db, "query", side_effect=query_once_empty),
            patch.object(db, "commit", side_effect=failing_commit),
        ):
            with pytest.raises(IntegrityError):
                _ingest_image(
                    filename="unrelated.png",
                    content_type="image/png",
                    file_data=data,
                    db=db,
                )

        # Session must still work afterward, not just for file_hash races.
        next_result = _ingest_image(
            filename="after.png",
            content_type="image/png",
            file_data=get_valid_image_bytes(color="yellow"),
            db=db,
        )
        assert next_result["status"] == "uploaded"


class TestBatchSessionRecovery:
    """A failure on one file must not fail the rest of the batch.

    The file_hash race above is the reachable trigger, but any commit failure
    leaves the shared session inactive -- an unexpected constraint violation, a
    dropped connection. The generic handlers have to clear it too, or the first
    unlucky file takes every later one with it.
    """

    def _zip_of(self, names_and_bytes):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "a", zipfile.ZIP_DEFLATED) as archive:
            for name, data in names_and_bytes:
                archive.writestr(name, data)
        buffer.seek(0)
        return buffer.read()

    def test_bulk_upload_survives_a_non_hash_commit_failure(self, client):
        payload = self._zip_of(
            [
                ("first.png", get_valid_image_bytes(color="red")),
                ("second.png", get_valid_image_bytes(color="blue")),
            ]
        )

        real_ingest = _ingest_image
        calls = {"n": 0}

        def poison_first_commit(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                db = kwargs["db"]
                # Land the session in exactly the state a failed flush leaves
                # it in, without pretending the error came from file_hash.
                db.add(Media(file_hash=None, minio_key="k", filename="bad"))
                try:
                    db.commit()
                except Exception as exc:
                    raise RuntimeError("commit failed") from exc
            return real_ingest(**kwargs)

        with patch(
            "find_api.routers.upload._ingest_image", side_effect=poison_first_commit
        ):
            response = client.post(
                "/api/upload/bulk",
                files=[("file", ("images.zip", payload, "application/zip"))],
            )

        assert response.status_code == 200
        results = {r["filename"]: r["status"] for r in response.json()["results"]}

        assert results["first.png"] == "failed"
        # The whole point: the unrelated second file still goes through.
        assert results["second.png"] == "uploaded"


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
