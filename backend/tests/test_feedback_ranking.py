"""Tests for the job that turns likes and search ratings into ranking boosts."""

import hashlib
from unittest.mock import patch

import pytest

from find_api.models.feedback import GeneralFeedback
from find_api.models.media import Media
from find_api.workers.jobs import process_feedback_ranking


def _seed_media(db, filename: str, *, liked=False, status="indexed") -> Media:
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        liked=liked,
        ranking_boost=0.0,
    )
    db.add(media)
    db.commit()
    return media


def _rate(db, media: Media, *ratings: int, feedback_type="search_rating"):
    for rating in ratings:
        db.add(
            GeneralFeedback(
                feedback_type=feedback_type, media_id=media.id, rating=rating
            )
        )
    db.commit()


def _run_job(db):
    session_factory = type(db)
    with (
        patch(
            "find_api.workers.jobs.SessionLocal",
            side_effect=lambda: session_factory(bind=db.get_bind()),
        ),
        patch("find_api.workers.jobs.clear_feedback_ranking_job_state"),
    ):
        assert process_feedback_ranking() == {"status": "success"}
    db.expire_all()


def test_boost_combines_likes_and_search_ratings(db):
    plain = _seed_media(db, "plain.jpg")
    liked = _seed_media(db, "liked.jpg", liked=True)
    loved = _seed_media(db, "loved.jpg", liked=True)
    disliked = _seed_media(db, "disliked.jpg")
    _rate(db, loved, 5, 4)
    _rate(db, disliked, 1, 1)
    # Only search ratings count towards ranking.
    _rate(db, plain, 5, feedback_type="caption_rating")

    _run_job(db)

    assert plain.ranking_boost == pytest.approx(0.0)
    assert liked.ranking_boost == pytest.approx(0.02)
    # 0.02 for the like plus (4.5 - 3) * 0.01, capped at 0.05.
    assert loved.ranking_boost == pytest.approx(0.035)
    assert disliked.ranking_boost == pytest.approx(-0.02)


def test_boost_is_capped_and_skips_unindexed_media(db):
    best = _seed_media(db, "best.jpg", liked=True)
    worst = _seed_media(db, "worst.jpg")
    pending = _seed_media(db, "pending.jpg", liked=True, status="pending")
    _rate(db, best, *[5] * 4)
    _rate(db, worst, *[1] * 4)
    # Pull the extremes past the cap: +0.02 like, +0.02 rating = 0.04, so add a
    # stronger signal by rating far outside the 1-5 range.
    _rate(db, best, 50)
    _rate(db, worst, -50)

    _run_job(db)

    assert best.ranking_boost == pytest.approx(0.05)
    assert worst.ranking_boost == pytest.approx(-0.05)
    assert pending.ranking_boost == pytest.approx(0.0)


def test_job_does_not_read_the_library_into_memory(db, count_selects):
    for index in range(5):
        _rate(db, _seed_media(db, f"bulk-{index}.jpg", liked=True), 4)

    assert count_selects(lambda: _run_job(db)) == 0
