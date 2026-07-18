import io
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from find_api.core.storage import (
    THUMBNAIL_CONTENT_TYPE,
    generate_thumbnail,
    upload_thumbnail,
)
from find_api.models.media import Media
from find_api.workers.jobs import analyze_image, generate_thumbnail_for_media


def _image_bytes(size=(1024, 768), color="blue"):
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_generate_thumbnail_creates_small_webp():
    thumbnail_data, width, height = generate_thumbnail(_image_bytes())

    assert thumbnail_data.startswith(b"RIFF")
    assert max(width, height) <= 256
    assert width == 256
    assert height == 192


def test_upload_thumbnail_returns_metadata_and_uploads_webp():
    data = _image_bytes()
    file_hash = hashlib.sha256(data).hexdigest()
    fake_backend = AsyncMock()

    with patch("find_api.core.storage.get_storage_instance", return_value=fake_backend):
        metadata = upload_thumbnail(data, file_hash)

    assert metadata["thumbnail_key"] == f"thumbnails/{file_hash[:2]}/{file_hash}.webp"
    assert metadata["thumbnail_content_type"] == THUMBNAIL_CONTENT_TYPE
    assert metadata["thumbnail_size"] > 0
    assert metadata["thumbnail_width"] == 256
    assert metadata["thumbnail_height"] == 192
    fake_backend.upload_file.assert_awaited_once()
    assert fake_backend.upload_file.call_args.args[2] == THUMBNAIL_CONTENT_TYPE


def test_upload_thumbnail_generation_failure_returns_none():
    fake_backend = AsyncMock()

    with patch(
        "find_api.core.storage_thumbnails.generate_thumbnail",
        side_effect=OSError("decode failed"),
    ), patch("find_api.core.storage.get_storage_instance", return_value=fake_backend):
        metadata = upload_thumbnail(b"not an image", "abc123")

    assert metadata is None
    fake_backend.upload_file.assert_not_awaited()


def test_upload_thumbnail_storage_failure_returns_none():
    fake_backend = AsyncMock()
    fake_backend.upload_file.side_effect = RuntimeError("down")

    with patch("find_api.core.storage.get_storage_instance", return_value=fake_backend):
        metadata = upload_thumbnail(_image_bytes(), "abc123")

    assert metadata is None


def test_analyze_image_backfills_missing_thumbnail(db):
    data = _image_bytes()
    file_hash = hashlib.sha256(data).hexdigest()
    media = Media(
        file_hash=file_hash,
        minio_key="images/ab/test.png",
        filename="test.png",
        content_type="image/png",
        file_size=len(data),
        status="pending",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    media_id = media.id

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch(
            "find_api.workers.jobs._begin_worker_runtime",
            return_value=(SimpleNamespace(applied_mode="full"), None),
        ),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch(
            "find_api.workers.jobs.upload_thumbnail",
            return_value={
                "thumbnail_key": "thumbnails/ab/test.webp",
                "thumbnail_content_type": "image/webp",
                "thumbnail_size": 256,
                "thumbnail_width": 256,
                "thumbnail_height": 192,
            },
        ) as upload_thumb,
        patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value={"caption": "test", "objects": [], "ocr_text": ""},
        ),
        patch(
            "find_api.workers.processors.generate_hybrid_embedding", return_value="[]"
        ),
        patch("find_api.workers.processors.has_person_object", return_value=False),
        patch("find_api.workers.jobs.enqueue_clustering_job"),
    ):
        result = analyze_image(media_id)

    updated = db.query(Media).filter(Media.id == media_id).one()
    assert result["status"] == "success"
    assert updated.thumbnail_key == "thumbnails/ab/test.webp"
    upload_thumb.assert_called_once_with(data, file_hash)


def test_analyze_image_keeps_existing_thumbnail(db):
    data = _image_bytes()
    file_hash = hashlib.sha256(data).hexdigest()
    media = Media(
        file_hash=file_hash,
        minio_key="images/ab/test.png",
        thumbnail_key="thumbnails/ab/existing.webp",
        filename="test.png",
        content_type="image/png",
        file_size=len(data),
        status="pending",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    media_id = media.id

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch(
            "find_api.workers.jobs._begin_worker_runtime",
            return_value=(SimpleNamespace(applied_mode="full"), None),
        ),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch("find_api.workers.jobs.upload_thumbnail") as upload_thumb,
        patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value={"caption": "test", "objects": [], "ocr_text": ""},
        ),
        patch(
            "find_api.workers.processors.generate_hybrid_embedding", return_value="[]"
        ),
        patch("find_api.workers.processors.has_person_object", return_value=False),
        patch("find_api.workers.jobs.enqueue_clustering_job"),
    ):
        result = analyze_image(media_id)

    updated = db.query(Media).filter(Media.id == media_id).one()
    assert result["status"] == "success"
    assert updated.thumbnail_key == "thumbnails/ab/existing.webp"
    upload_thumb.assert_not_called()


def test_analyze_image_metadata_only_mode_never_imports_ai_pipeline(db):
    data = _image_bytes(size=(64, 48))
    file_hash = hashlib.sha256(data).hexdigest()
    media = Media(
        file_hash=file_hash,
        minio_key="images/ab/metadata-only.png",
        thumbnail_key="thumbnails/ab/existing.webp",
        filename="metadata-only.png",
        content_type="image/png",
        file_size=len(data),
        status="pending",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    media_id = media.id

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch("find_api.core.runtime_profile.settings.FIND_BUILD_PROFILE", "no-ai"),
        patch("find_api.core.runtime_profile.settings.ML_MODE", "disabled"),
        patch("find_api.core.runtime_profile.settings.AI_ENABLED", False),
        patch("find_api.workers.jobs.enqueue_clustering_job") as enqueue_cluster,
    ):
        result = analyze_image(media_id)

    updated = db.query(Media).filter(Media.id == media_id).one()
    assert result["mode"] == "disabled"
    assert updated.status == "indexed"
    assert updated.vector is None
    assert updated.metadata_json["ai_disabled"] is True
    assert updated.width == 64
    assert updated.height == 48
    enqueue_cluster.assert_not_called()


def test_generate_thumbnail_for_media_backfills_without_full_analysis(db):
    data = _image_bytes()
    file_hash = hashlib.sha256(data).hexdigest()
    media = Media(
        file_hash=file_hash,
        minio_key="images/ab/test.png",
        filename="test.png",
        content_type="image/png",
        file_size=len(data),
        status="indexed",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    media_id = media.id

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch(
            "find_api.workers.jobs.upload_thumbnail",
            return_value={
                "thumbnail_key": "thumbnails/ab/backfilled.webp",
                "thumbnail_content_type": "image/webp",
                "thumbnail_size": 256,
                "thumbnail_width": 256,
                "thumbnail_height": 192,
            },
        ) as upload_thumb,
    ):
        result = generate_thumbnail_for_media(media_id)

    updated = db.query(Media).filter(Media.id == media_id).one()
    assert result == {"status": "success", "media_id": media_id}
    assert updated.thumbnail_key == "thumbnails/ab/backfilled.webp"
    upload_thumb.assert_called_once_with(data, file_hash)


def test_generate_thumbnail_for_media_skips_existing_thumbnail(db):
    media = Media(
        file_hash="abc123",
        minio_key="images/ab/test.png",
        thumbnail_key="thumbnails/ab/existing.webp",
        filename="test.png",
        content_type="image/png",
        file_size=123,
        status="indexed",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    media_id = media.id

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch("find_api.workers.jobs.get_file") as get_file_mock,
        patch("find_api.workers.jobs.upload_thumbnail") as upload_thumb,
    ):
        result = generate_thumbnail_for_media(media_id)

    assert result == {"status": "skipped", "media_id": media_id, "reason": "exists"}
    get_file_mock.assert_not_called()
    upload_thumb.assert_not_called()
