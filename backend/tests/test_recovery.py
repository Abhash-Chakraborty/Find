"""Tests for abandoned analysis job reconciliation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

import find_api.core.recovery as recovery_module
from find_api.core.recovery import (
    RECOVERY_ERROR_MESSAGE,
    reconcile_abandoned_analysis_jobs,
)


class Base(DeclarativeBase):
    pass


class FakeMedia(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    minio_key: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exif_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def reset_db():
    db = TestingSessionLocal()
    db.query(FakeMedia).delete()
    db.commit()
    db.close()
    yield


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_media(db, *, status: str, created_at: datetime) -> FakeMedia:
    media = FakeMedia(
        file_hash=f"{status}-{created_at.timestamp()}",
        minio_key="images/ab/test.jpg",
        filename="test.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        created_at=created_at,
        processed_at=created_at if status == "indexed" else None,
        error_message="existing failure" if status == "failed" else None,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def test_stale_pending_media_is_marked_failed(db):
    old_time = datetime.now(timezone.utc) - timedelta(seconds=1800)

    with patch.object(recovery_module, "Media", FakeMedia):
        media = make_media(db, status="pending", created_at=old_time)

        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 1
    assert media.status == "failed"
    assert media.error_message == RECOVERY_ERROR_MESSAGE
    assert media.processed_at is None


def test_stale_processing_media_is_marked_failed(db):
    old_time = datetime.now(timezone.utc) - timedelta(seconds=1800)

    with patch.object(recovery_module, "Media", FakeMedia):
        media = make_media(db, status="processing", created_at=old_time)

        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 1
    assert media.status == "failed"
    assert media.error_message == RECOVERY_ERROR_MESSAGE


def test_fresh_pending_and_processing_media_stay_active(db):
    fresh_time = datetime.now(timezone.utc)

    with patch.object(recovery_module, "Media", FakeMedia):
        pending = make_media(db, status="pending", created_at=fresh_time)
        processing = make_media(db, status="processing", created_at=fresh_time)

        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(pending)
    db.refresh(processing)
    assert reconciled == 0
    assert pending.status == "pending"
    assert processing.status == "processing"


def test_indexed_and_failed_media_are_unchanged(db):
    old_time = datetime.now(timezone.utc) - timedelta(seconds=1800)

    with patch.object(recovery_module, "Media", FakeMedia):
        indexed = make_media(db, status="indexed", created_at=old_time)
        failed = make_media(db, status="failed", created_at=old_time)

        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(indexed)
    db.refresh(failed)
    assert reconciled == 0
    assert indexed.status == "indexed"
    assert failed.status == "failed"
    assert failed.error_message == "existing failure"