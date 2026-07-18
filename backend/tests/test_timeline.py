"""Tests for timeline bucket endpoints (Phase 3.1)."""

import hashlib
from datetime import datetime, timezone

from find_api.models.media import Media


def _seed(
    db,
    *,
    filename,
    created_at,
    status="indexed",
    liked=False,
    is_hidden=False,
    is_archived=False,
    deleted_at=None,
    width=800,
    height=600,
):
    media = Media(
        file_hash=hashlib.sha256(filename.encode()).hexdigest(),
        minio_key=f"images/test/{filename}",
        filename=filename,
        content_type="image/jpeg",
        file_size=1024,
        status=status,
        liked=liked,
        width=width,
        height=height,
        is_hidden=is_hidden,
        is_archived=is_archived,
        deleted_at=deleted_at,
        vault_state="hidden_encrypted" if is_hidden else "visible",
        created_at=created_at,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def _dt(year, month, day=15):
    return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)


class TestTimelineBuckets:
    """GET /api/timeline/buckets"""

    def test_empty(self, client):
        body = client.get("/api/timeline/buckets").json()
        assert body == {"buckets": [], "total": 0}

    def test_groups_by_month_with_counts(self, client, db):
        _seed(db, filename="a.jpg", created_at=_dt(2026, 3, 1))
        _seed(db, filename="b.jpg", created_at=_dt(2026, 3, 20))
        _seed(db, filename="c.jpg", created_at=_dt(2026, 1, 5))

        body = client.get("/api/timeline/buckets").json()

        assert body["total"] == 3
        assert body["buckets"] == [
            {"timeBucket": "2026-03-01", "count": 2},
            {"timeBucket": "2026-01-01", "count": 1},
        ]

    def test_order_oldest_first(self, client, db):
        _seed(db, filename="a.jpg", created_at=_dt(2026, 3, 1))
        _seed(db, filename="c.jpg", created_at=_dt(2026, 1, 5))

        body = client.get("/api/timeline/buckets", params={"order": "oldest"}).json()

        assert [b["timeBucket"] for b in body["buckets"]] == [
            "2026-01-01",
            "2026-03-01",
        ]

    def test_excludes_archived_and_trashed(self, client, db):
        _seed(db, filename="visible.jpg", created_at=_dt(2026, 3, 1))
        _seed(db, filename="arch.jpg", created_at=_dt(2026, 3, 2), is_archived=True)
        _seed(
            db,
            filename="trash.jpg",
            created_at=_dt(2026, 3, 3),
            deleted_at=_dt(2026, 4, 1),
        )
        _seed(db, filename="hidden.jpg", created_at=_dt(2026, 3, 4), is_hidden=True)

        body = client.get("/api/timeline/buckets").json()

        assert body["total"] == 1
        assert body["buckets"] == [{"timeBucket": "2026-03-01", "count": 1}]

    def test_liked_filter(self, client, db):
        _seed(db, filename="liked.jpg", created_at=_dt(2026, 3, 1), liked=True)
        _seed(db, filename="plain.jpg", created_at=_dt(2026, 3, 2), liked=False)

        body = client.get("/api/timeline/buckets", params={"liked": "true"}).json()

        assert body["total"] == 1


class TestTimelineBucket:
    """GET /api/timeline/bucket"""

    def test_returns_columnar_arrays_for_month(self, client, db):
        a = _seed(
            db, filename="a.jpg", created_at=_dt(2026, 3, 1), width=1600, height=900
        )
        b = _seed(
            db, filename="b.jpg", created_at=_dt(2026, 3, 20), width=600, height=800
        )
        # Different month — must be excluded.
        _seed(db, filename="other.jpg", created_at=_dt(2026, 1, 5))

        body = client.get(
            "/api/timeline/bucket", params={"timeBucket": "2026-03"}
        ).json()

        assert body["timeBucket"] == "2026-03-01"
        assert body["count"] == 2
        # newest-first default → b (Mar 20) before a (Mar 1)
        assert body["id"] == [b.id, a.id]
        assert body["ratio"] == [0.75, round(1600 / 900, 4)]
        assert body["thumbhash"] == [None, None]
        assert body["liked"] == [False, False]
        assert body["thumbnailUrl"] == [
            f"/api/image/{b.id}/thumbnail",
            f"/api/image/{a.id}/thumbnail",
        ]

    def test_accepts_full_date_bucket_key(self, client, db):
        _seed(db, filename="a.jpg", created_at=_dt(2026, 3, 1))

        body = client.get(
            "/api/timeline/bucket", params={"timeBucket": "2026-03-01"}
        ).json()

        assert body["count"] == 1

    def test_oldest_order(self, client, db):
        a = _seed(db, filename="a.jpg", created_at=_dt(2026, 3, 1))
        b = _seed(db, filename="b.jpg", created_at=_dt(2026, 3, 20))

        body = client.get(
            "/api/timeline/bucket",
            params={"timeBucket": "2026-03", "order": "oldest"},
        ).json()

        assert body["id"] == [a.id, b.id]

    def test_excludes_archived_and_trashed(self, client, db):
        keep = _seed(db, filename="keep.jpg", created_at=_dt(2026, 3, 1))
        _seed(db, filename="arch.jpg", created_at=_dt(2026, 3, 2), is_archived=True)
        _seed(
            db,
            filename="trash.jpg",
            created_at=_dt(2026, 3, 3),
            deleted_at=_dt(2026, 4, 1),
        )

        body = client.get(
            "/api/timeline/bucket", params={"timeBucket": "2026-03"}
        ).json()

        assert body["id"] == [keep.id]

    def test_ratio_null_when_dimensions_missing(self, client, db):
        _seed(db, filename="a.jpg", created_at=_dt(2026, 3, 1), width=None, height=None)

        body = client.get(
            "/api/timeline/bucket", params={"timeBucket": "2026-03"}
        ).json()

        assert body["ratio"] == [None]

    def test_invalid_bucket_returns_422(self, client):
        response = client.get(
            "/api/timeline/bucket", params={"timeBucket": "not-a-date"}
        )
        assert response.status_code == 422

    def test_empty_month(self, client, db):
        _seed(db, filename="a.jpg", created_at=_dt(2026, 1, 1))

        body = client.get(
            "/api/timeline/bucket", params={"timeBucket": "2026-03"}
        ).json()

        assert body["count"] == 0
        assert body["id"] == []
