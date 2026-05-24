"""
Tests for the POST /image/{media_id}/reprocess endpoint.

Run with (from backend/ directory):
    $env:PYTHONPATH = "src"
    pytest tests/test_reprocess.py -v
"""

import datetime
from typing import Optional
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
import find_api.routers.gallery as gallery_module
from find_api.core.database import get_db
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Minimal in-memory SQLite replica of the Media model (no pgvector needed)
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class FakeMedia(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    minio_key: Mapped[str] = mapped_column(String(255))
    thumbnail_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thumbnail_content_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    thumbnail_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    analysis_job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    processed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exif_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cluster_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


Base.metadata.create_all(bind=engine)


def get_test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fresh_db():
    return TestingSessionLocal()


# ---------------------------------------------------------------------------
# Import the router under test and override dependencies
# Patch find_api.routers.gallery.Media so the router uses our FakeMedia.
# ---------------------------------------------------------------------------

gallery_module.Media = FakeMedia  # type: ignore[assignment]

test_app = FastAPI()
test_app.include_router(gallery_module.router, prefix="/api")
test_app.dependency_overrides[get_db] = get_test_db


@pytest.fixture(autouse=True)
def reset_db():
    """Truncate the media table between tests."""
    db = _fresh_db()
    db.query(FakeMedia).delete()
    db.commit()
    db.close()
    yield


@pytest.fixture()
def client():
    with TestClient(test_app) as c:
        yield c


def make_media(
    *, status: str, metadata_json=None, error_message=None, thumbnail_key=None
) -> FakeMedia:
    db = _fresh_db()
    m = FakeMedia(
        file_hash="abc123",
        minio_key="images/ab/abc123.jpg",
        filename="test.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        metadata_json=metadata_json,
        error_message=error_message,
        thumbnail_key=thumbnail_key,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    db.close()
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReprocessEndpoint:
    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_failed_image_returns_queued(self, mock_queue, client):
        """Failed image is accepted; response contains job_id and status=queued."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-001"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(status="failed", error_message="some error")

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 200
        body = resp.json()
        assert body["media_id"] == media.id
        assert body["job_id"] == "fake-job-001"
        assert body["status"] == "queued"

    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_clears_error_and_resets_status(self, mock_queue, client):
        """After reprocess: status must be pending, error_message must be None."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-002"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(status="failed", error_message="old error")

        client.post(f"/api/image/{media.id}/reprocess")

        db = _fresh_db()
        updated = db.query(FakeMedia).filter(FakeMedia.id == media.id).first()
        assert updated.status == "pending"
        assert updated.error_message is None
        assert updated.processed_at is None
        db.close()

    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_persists_latest_analysis_job_id(self, mock_queue, client):
        mock_job = MagicMock()
        mock_job.id = "fake-job-latest"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(status="failed", error_message="old error")

        client.post(f"/api/image/{media.id}/reprocess")

        db = _fresh_db()
        updated = db.query(FakeMedia).filter(FakeMedia.id == media.id).first()
        assert updated.analysis_job_id == "fake-job-latest"
        db.close()

    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_indexed_incomplete_no_caption(self, mock_queue, client):
        """Indexed image with no caption is eligible for reprocessing."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-003"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(status="indexed", metadata_json={"objects": []})

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_reprocess_indexed_complete_is_rejected(self, client):
        """Indexed image with a caption must return 400 — no spurious retries."""
        media = make_media(
            status="indexed",
            metadata_json={"caption": "a dog on a bench", "objects": []},
            thumbnail_key="thumbnails/ab/abc123.webp",
        )

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 400

    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_indexed_missing_thumbnail(self, mock_queue, client):
        """Indexed image missing a thumbnail is eligible for backfill."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-thumbnail"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(
            status="indexed",
            metadata_json={"caption": "a dog on a bench", "objects": []},
            thumbnail_key=None,
        )

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_reprocess_pending_image_is_rejected(self, client):
        """Already-pending image must not be double-enqueued."""
        media = make_media(status="pending")

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 400

    def test_reprocess_processing_image_is_rejected(self, client):
        """Currently-processing image must not be requeued."""
        media = make_media(status="processing")

        resp = client.post(f"/api/image/{media.id}/reprocess")

        assert resp.status_code == 400

    def test_reprocess_nonexistent_media_returns_404(self, client):
        """Unknown media_id returns 404."""
        resp = client.post("/api/image/99999/reprocess")

        assert resp.status_code == 404

    @patch("find_api.routers.gallery.get_task_queue")
    def test_reprocess_enqueues_analyze_image_job(self, mock_queue, client):
        """The RQ queue must receive exactly one enqueue call with correct args."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-004"
        mock_queue_instance = MagicMock()
        mock_queue_instance.enqueue.return_value = mock_job
        mock_queue.return_value = mock_queue_instance

        media = make_media(status="failed")

        client.post(f"/api/image/{media.id}/reprocess")

        mock_queue_instance.enqueue.assert_called_once()
        call_args = mock_queue_instance.enqueue.call_args
        from find_api.workers.jobs import analyze_image

        assert call_args[0][0] is analyze_image
        assert call_args[0][1] == media.id

    @patch("find_api.routers.gallery.get_task_queue")
    def test_repeated_reprocess_allowed(self, mock_queue, client):
        """A failed image may be retried multiple times."""
        mock_job = MagicMock()
        mock_job.id = "fake-job-005"
        mock_queue.return_value.enqueue.return_value = mock_job

        media = make_media(status="failed")

        r1 = client.post(f"/api/image/{media.id}/reprocess")
        assert r1.status_code == 200

        # Simulate second failure
        db = _fresh_db()
        item = db.query(FakeMedia).filter(FakeMedia.id == media.id).first()
        item.status = "failed"
        item.error_message = "failed again"
        db.commit()
        db.close()

        r2 = client.post(f"/api/image/{media.id}/reprocess")
        assert r2.status_code == 200
