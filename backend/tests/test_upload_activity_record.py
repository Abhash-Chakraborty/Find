"""One upload job must leave exactly one ``upload.*`` row behind.

``upload.completed`` used to be recorded straight after the indexing commit, while
``detect_and_store_faces`` still ran afterwards outside any ``try``. A failure there
reached the outer handler, which appended ``upload.failed`` for the same media, and the
feed carried two contradictory rows for a single job.
"""

import hashlib
import io as _io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from find_api.models.activity import Activity
from find_api.models.media import Media
from find_api.workers.jobs import analyze_image


def _image_bytes(size=(64, 48), color="blue"):
    image = Image.new("RGB", size, color=color)
    buffer = _io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _media(db, data):
    media = Media(
        file_hash=hashlib.sha256(data).hexdigest(),
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
    return media.id


def _upload_actions(db, media_id):
    rows = (
        db.query(Activity)
        .filter(Activity.category == "upload", Activity.media_id == media_id)
        .all()
    )
    return sorted(row.action for row in rows)


def test_face_detection_failure_records_only_upload_failed(db):
    data = _image_bytes()
    media_id = _media(db, data)

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch(
            "find_api.workers.jobs._begin_worker_runtime",
            return_value=(
                SimpleNamespace(
                    applied_mode="full", map_enabled=False, build_profile="cpu"
                ),
                None,
            ),
        ),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value={"caption": "test", "objects": [], "ocr_text": ""},
        ),
        patch(
            "find_api.workers.processors.generate_hybrid_embedding", return_value=None
        ),
        patch("find_api.workers.processors.has_person_object", return_value=True),
        patch(
            "find_api.workers.processors.detect_and_store_faces",
            side_effect=RuntimeError("face model exploded"),
        ),
        patch("find_api.workers.jobs.enqueue_clustering_job"),
    ):
        with pytest.raises(RuntimeError):
            analyze_image(media_id)

    assert _upload_actions(db, media_id) == ["failed"]


def test_successful_job_records_exactly_one_completed(db):
    """The control: moving the record must not drop it from the path that works."""
    data = _image_bytes()
    media_id = _media(db, data)

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch(
            "find_api.workers.jobs._begin_worker_runtime",
            return_value=(
                SimpleNamespace(
                    applied_mode="full", map_enabled=False, build_profile="cpu"
                ),
                None,
            ),
        ),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value={"caption": "test", "objects": [], "ocr_text": ""},
        ),
        patch(
            "find_api.workers.processors.generate_hybrid_embedding", return_value=None
        ),
        patch("find_api.workers.processors.has_person_object", return_value=True),
        patch("find_api.workers.processors.detect_and_store_faces", return_value=0),
        patch("find_api.workers.jobs.enqueue_clustering_job"),
    ):
        result = analyze_image(media_id)

    assert result["status"] == "success"
    assert _upload_actions(db, media_id) == ["completed"]


def test_metadata_only_mode_still_records_completed(db):
    """The disabled-mode early return is the other success exit and needs the row too."""
    data = _image_bytes()
    media_id = _media(db, data)

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=db),
        patch(
            "find_api.workers.jobs._begin_worker_runtime",
            return_value=(
                SimpleNamespace(
                    applied_mode="disabled", map_enabled=False, build_profile="cpu"
                ),
                None,
            ),
        ),
        patch("find_api.workers.jobs.get_current_job", return_value=None),
        patch("find_api.workers.jobs.get_file", return_value=data),
        patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value={"caption": "test", "objects": [], "ocr_text": ""},
        ),
        patch(
            "find_api.workers.processors.generate_hybrid_embedding", return_value=None
        ),
    ):
        result = analyze_image(media_id)

    assert result["mode"] == "disabled"
    assert _upload_actions(db, media_id) == ["completed"]
