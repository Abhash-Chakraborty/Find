"""Performance acceptance for the timeline hot path (plan §10.3, Appendix §E).

Seeds a large synthetic library and measures the two endpoints the justified
grid + scrubber depend on, end-to-end through the live ASGI app:

- ``GET /api/timeline/buckets`` — the aggregate the client needs *before* it can
  draw the scrollbar / compute total height. Must stay fast as the library grows.
- ``GET /api/timeline/bucket`` — one month's columnar window, the per-scroll fetch.

**Honesty about the environment:** this runs against in-memory SQLite through
``TestClient`` (the test harness), not Postgres on real hardware. It therefore
validates *query shape and payload assembly* scaling — it catches an accidental
N+1, a missing index assumption, or a per-row Python blowup — but the absolute
millisecond numbers are not a substitute for the live-stack / low-end-profile
acceptance run still owed in §10.3/§5.4. Budgets below are deliberately set with
headroom so this is a regression tripwire, not a benchmark.
"""

import hashlib
import time
from datetime import datetime, timezone

import pytest

from find_api.models.media import Media

# Synthetic library size. Large enough to expose super-linear behavior, small
# enough to keep the suite fast (seeding dominates, not the measured calls).
LIBRARY_SIZE = 10_000
MONTHS = 24  # spread across two years → ~417 assets/month

# Budgets (in-memory SQLite via TestClient). Tripwires, not benchmarks.
BUCKETS_BUDGET_S = 1.0  # the whole-library month aggregate
BUCKET_BUDGET_S = 1.0  # one month's columnar window (~417 rows)


def _seed_library(db, n: int, months: int) -> None:
    """Bulk-insert ``n`` browsable media rows spread across ``months`` months."""
    rows = []
    for i in range(n):
        month = (i % months) + 1
        year = 2024 + (month - 1) // 12
        m = ((month - 1) % 12) + 1
        # Vary day so ordering within a month is meaningful.
        day = (i % 27) + 1
        created = datetime(year, m, day, 12, 0, 0, tzinfo=timezone.utc)
        rows.append(
            Media(
                file_hash=hashlib.sha256(f"perf-{i}".encode()).hexdigest(),
                minio_key=f"images/perf/{i}.jpg",
                thumbnail_key=f"thumbnails/perf/{i}.webp",
                filename=f"perf-{i}.jpg",
                content_type="image/jpeg",
                file_size=2048,
                status="indexed",
                width=1600 + (i % 5) * 100,
                height=1200,
                liked=(i % 10 == 0),
                is_hidden=False,
                is_archived=False,
                deleted_at=None,
                vault_state="visible",
                created_at=created,
            )
        )
    db.bulk_save_objects(rows)
    db.commit()


@pytest.fixture()
def seeded(db):
    _seed_library(db, LIBRARY_SIZE, MONTHS)
    return db


def _time(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


class TestTimelinePerf:
    def test_buckets_aggregate_under_budget(self, client, seeded, capsys):
        resp, elapsed = _time(lambda: client.get("/api/timeline/buckets"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == LIBRARY_SIZE
        assert len(body["buckets"]) == MONTHS
        with capsys.disabled():
            print(
                f"\n[perf] /timeline/buckets over {LIBRARY_SIZE} assets, "
                f"{MONTHS} months: {elapsed * 1000:.1f} ms "
                f"(budget {BUCKETS_BUDGET_S * 1000:.0f} ms)"
            )
        assert (
            elapsed < BUCKETS_BUDGET_S
        ), f"/timeline/buckets took {elapsed:.3f}s (budget {BUCKETS_BUDGET_S}s)"

    def test_single_bucket_window_under_budget(self, client, seeded, capsys):
        # Pick a month that actually has assets.
        first = client.get("/api/timeline/buckets").json()["buckets"][0]["timeBucket"]
        month_key = first[:7]  # YYYY-MM
        resp, elapsed = _time(
            lambda: client.get(f"/api/timeline/bucket?timeBucket={month_key}")
        )
        assert resp.status_code == 200
        body = resp.json()
        # Columnar arrays are parallel and well-formed.
        assert body["count"] == len(body["id"]) == len(body["ratio"])
        assert len(body["thumbnailUrl"]) == body["count"]
        assert body["count"] > 0
        with capsys.disabled():
            print(
                f"\n[perf] /timeline/bucket ({month_key}, {body['count']} assets): "
                f"{elapsed * 1000:.1f} ms (budget {BUCKET_BUDGET_S * 1000:.0f} ms)"
            )
        assert (
            elapsed < BUCKET_BUDGET_S
        ), f"/timeline/bucket took {elapsed:.3f}s (budget {BUCKET_BUDGET_S}s)"

    def test_liked_filter_aggregate_under_budget(self, client, seeded):
        # The favorites filter must not change the query's scaling characteristics.
        resp, elapsed = _time(lambda: client.get("/api/timeline/buckets?liked=true"))
        assert resp.status_code == 200
        # 1 in 10 seeded assets is liked.
        assert resp.json()["total"] == LIBRARY_SIZE // 10
        assert elapsed < BUCKETS_BUDGET_S
