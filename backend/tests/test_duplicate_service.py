"""Tests for near-duplicate detection services and endpoints."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pytest

from find_api.models.media import Media
from find_api.services.duplicate_service import (
    flag_as_duplicate,
    find_near_duplicate,
)


def _seed_media(db, *, filename: str, duplicate_of: int | None = None) -> Media:
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status="indexed",
        width=800,
        height=600,
        thumbnail_key=f"thumbnails/test/{filename}.webp",
        thumbnail_content_type="image/webp",
        thumbnail_size=512,
        thumbnail_width=256,
        thumbnail_height=192,
        duplicate_of=duplicate_of,
        created_at=datetime.now(timezone.utc),
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


class _FakeResult:
    def __init__(self, row: tuple[int, float] | None):
        self.row = row

    def fetchone(self) -> tuple[int, float] | None:
        return self.row


class _FakeDb:
    def __init__(self, row: tuple[int, float] | None):
        self.row = row
        self.statements: list[str] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None):
        self.statements.append(str(statement))
        return _FakeResult(self.row)


class _FailingDb:
    def __init__(self):
        self.rolled_back = False

    def execute(self, statement: Any, params: dict[str, Any] | None = None):
        raise RuntimeError("database failed")

    def rollback(self):
        self.rolled_back = True


def test_find_near_duplicate_returns_match_above_threshold():
    db = _FakeDb((42, 0.98))

    result = find_near_duplicate(db, media_id=7, embedding=[0.1, 0.2, 0.3])

    assert result == 42
    assert "user_id" not in db.statements[0]
    assert "id != :media_id" in db.statements[0]


def test_find_near_duplicate_ignores_match_below_threshold():
    db = _FakeDb((42, 0.96))

    result = find_near_duplicate(db, media_id=7, embedding=[0.1, 0.2, 0.3])

    assert result is None


def test_find_near_duplicate_accepts_match_at_threshold():
    """Test boundary: exactly 0.97 similarity is a match (>= check)."""
    db = _FakeDb((42, 0.97))

    result = find_near_duplicate(db, media_id=7, embedding=[0.1, 0.2, 0.3])

    assert result == 42


def test_find_near_duplicate_handles_no_candidate():
    db = _FakeDb(None)

    result = find_near_duplicate(db, media_id=7, embedding=[0.1, 0.2, 0.3])

    assert result is None


def test_flag_as_duplicate_updates_media(db):
    original = _seed_media(db, filename="original.jpg")
    duplicate = _seed_media(db, filename="duplicate.jpg")

    flag_as_duplicate(db, media_id=duplicate.id, duplicate_of=original.id)

    db.refresh(duplicate)
    assert duplicate.duplicate_of == original.id


def test_flag_as_duplicate_rolls_back_on_error():
    db = _FailingDb()

    with pytest.raises(RuntimeError, match="database failed"):
        flag_as_duplicate(db, media_id=2, duplicate_of=1)

    assert db.rolled_back is True


def test_list_duplicates_paginates_pairs(client, db):
    first_original = _seed_media(db, filename="first-original.jpg")
    first_duplicate = _seed_media(
        db,
        filename="first-duplicate.jpg",
        duplicate_of=first_original.id,
    )
    second_original = _seed_media(db, filename="second-original.jpg")
    second_duplicate = _seed_media(
        db,
        filename="second-duplicate.jpg",
        duplicate_of=second_original.id,
    )

    response = client.get("/api/duplicates", params={"page": 1, "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["limit"] == 1
    assert body["items"] == [
        {
            "duplicate_id": second_duplicate.id,
            "duplicate_name": "second-duplicate.jpg",
            "original_id": second_original.id,
            "original_name": "second-original.jpg",
        }
    ]

    response = client.get("/api/duplicates", params={"page": 2, "limit": 1})

    assert response.status_code == 200
    assert response.json()["items"][0]["duplicate_id"] == first_duplicate.id


def test_keep_both_clears_duplicate_flag(client, db):
    original = _seed_media(db, filename="original.jpg")
    duplicate = _seed_media(
        db,
        filename="duplicate.jpg",
        duplicate_of=original.id,
    )

    response = client.post(f"/api/image/{duplicate.id}/keep")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    db.refresh(duplicate)
    assert duplicate.duplicate_of is None


def test_keep_both_returns_404_for_missing_media(client):
    response = client.post("/api/image/99999/keep")

    assert response.status_code == 404
    assert response.json()["detail"] == "Image not found"
