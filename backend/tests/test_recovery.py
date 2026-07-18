"""Tests for analysis-job reconciliation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from find_api.core.recovery import (
    INCOMPLETE_JOB_ERROR_MESSAGE,
    RECOVERY_ERROR_MESSAGE,
    reconcile_abandoned_analysis_jobs,
)
from find_api.models.media import Media


def make_media(
    db,
    *,
    status: str,
    analysis_job_id: str | None,
    created_at: datetime,
    updated_at: datetime | None = None,
) -> Media:
    media = Media(
        file_hash=f"{status}-{created_at.timestamp()}-{analysis_job_id or 'none'}",
        minio_key="images/ab/test.jpg",
        filename="test.jpg",
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        analysis_job_id=analysis_job_id,
        created_at=created_at,
        updated_at=updated_at,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def job_with_status(status: str) -> MagicMock:
    job = MagicMock()
    job.get_status.return_value = status
    return job


def test_failed_job_marks_media_failed(db):
    media = make_media(
        db,
        status="processing",
        analysis_job_id="failed-job",
        created_at=datetime.now(timezone.utc),
    )

    with patch(
        "find_api.core.recovery._get_job_status",
        return_value="failed",
    ):
        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 1
    assert media.status == "failed"
    assert media.error_message == RECOVERY_ERROR_MESSAGE


def test_finished_job_without_media_update_marks_media_failed(db):
    media = make_media(
        db,
        status="processing",
        analysis_job_id="finished-job",
        created_at=datetime.now(timezone.utc),
    )

    with patch(
        "find_api.core.recovery._get_job_status",
        return_value="finished",
    ):
        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 1
    assert media.status == "failed"
    assert media.error_message == INCOMPLETE_JOB_ERROR_MESSAGE


def test_active_job_does_not_false_fail_old_media(db):
    media = make_media(
        db,
        status="processing",
        analysis_job_id="started-job",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    with patch(
        "find_api.core.recovery._get_job_status",
        return_value="started",
    ):
        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 0
    assert media.status == "processing"
    assert media.error_message is None


def test_missing_old_job_marks_media_failed(db):
    media = make_media(
        db,
        status="pending",
        analysis_job_id="missing-job",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=1800),
    )

    with patch(
        "find_api.core.recovery._get_job_status",
        return_value=None,
    ):
        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 1
    assert media.status == "failed"
    assert media.error_message == RECOVERY_ERROR_MESSAGE


def test_missing_fresh_job_stays_active(db):
    media = make_media(
        db,
        status="pending",
        analysis_job_id="missing-job",
        created_at=datetime.now(timezone.utc),
    )

    with patch(
        "find_api.core.recovery._get_job_status",
        return_value=None,
    ):
        reconciled = reconcile_abandoned_analysis_jobs(db)

    db.refresh(media)
    assert reconciled == 0
    assert media.status == "pending"
    assert media.error_message is None
