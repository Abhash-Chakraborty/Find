"""Timeline endpoints — month-bucketed browsing for the justified grid UI.

Two endpoints back the timeline:

- ``GET /timeline/buckets`` returns an ordered list of month buckets with a
  count each, so the client can compute total scroll height and scrubber
  positions before loading any photo.
- ``GET /timeline/bucket`` returns the assets for one month as columnar
  parallel arrays (small payloads for large months on low-end clients).

Both reuse the same browse scoping as the gallery (not hidden, not archived,
not trashed) via :func:`_browsable_media_query`, plus the per-user IDOR guard.

v1 buckets by ``created_at`` (upload date). EXIF "date taken" and a populated
``thumbhash`` are deferred (see plan.md PROPOSED notes); ``thumbhash`` is wired
as a nullable field now so the contract is stable, and the justified grid lays
out from ``ratio`` (width/height) alone.
"""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session

from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user, scope_media_query
from find_api.models.media import Media
from find_api.models.user import User
from find_api.routers.gallery import _browsable_media_query, build_thumbnail_url

logger = logging.getLogger(__name__)

router = APIRouter()

TimelineOrder = Literal["newest", "oldest"]


def _compute_ratio(width: Optional[int], height: Optional[int]) -> Optional[float]:
    """Aspect ratio (w/h) used by the justified layout, or None if unknown."""
    if not width or not height:
        return None
    return round(width / height, 4)


def _parse_bucket(time_bucket: str) -> tuple[datetime, datetime]:
    """Parse a ``YYYY-MM`` or ``YYYY-MM-DD`` bucket key into a [start, end) month range."""
    raw = time_bucket.strip()
    fmt = "%Y-%m-%d" if raw.count("-") == 2 else "%Y-%m"
    try:
        parsed = datetime.strptime(raw, fmt)
    except ValueError as exc:
        raise HTTPException(
            422, "timeBucket must be 'YYYY-MM' or 'YYYY-MM-DD'."
        ) from exc

    start = datetime(parsed.year, parsed.month, 1, tzinfo=timezone.utc)
    if parsed.month == 12:
        end = datetime(parsed.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(parsed.year, parsed.month + 1, 1, tzinfo=timezone.utc)
    return start, end


@router.get("/timeline/buckets")
def get_timeline_buckets(
    order: TimelineOrder = Query("newest"),
    liked: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return month buckets with a count each, ordered newest- or oldest-first.

    Response: ``{ "buckets": [{ "timeBucket": "YYYY-MM-01", "count": int }], "total": int }``.
    """
    query = scope_media_query(_browsable_media_query(db), user)
    if liked is not None:
        query = query.filter(Media.liked == liked)

    # extract() compiles to EXTRACT on PostgreSQL and STRFTIME on SQLite, so
    # this month grouping is portable across the test and prod dialects.
    year_col = func.extract("year", Media.created_at)
    month_col = func.extract("month", Media.created_at)

    rows = (
        query.with_entities(
            year_col.label("year"),
            month_col.label("month"),
            func.count().label("count"),
        )
        .group_by(year_col, month_col)
        .all()
    )

    buckets = [
        {
            "timeBucket": f"{int(row.year):04d}-{int(row.month):02d}-01",
            "count": int(row.count),
        }
        for row in rows
        if row.year is not None and row.month is not None
    ]
    buckets.sort(key=lambda b: b["timeBucket"], reverse=(order == "newest"))

    return {"buckets": buckets, "total": sum(b["count"] for b in buckets)}


@router.get("/timeline/bucket")
def get_timeline_bucket(
    timeBucket: str = Query(..., description="Month key 'YYYY-MM' or 'YYYY-MM-DD'"),
    order: TimelineOrder = Query("newest"),
    liked: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return all assets in one month bucket as columnar parallel arrays.

    Columnar (parallel arrays keyed by index) keeps payloads compact for large
    months. Arrays returned: ``id``, ``ratio``, ``thumbhash`` (nullable),
    ``liked``, ``createdAt``, ``thumbnailUrl``.
    """
    start, end = _parse_bucket(timeBucket)

    query = scope_media_query(_browsable_media_query(db), user).filter(
        Media.created_at >= start,
        Media.created_at < end,
    )
    if liked is not None:
        query = query.filter(Media.liked == liked)

    ordering = desc(Media.created_at) if order == "newest" else asc(Media.created_at)
    media_list = query.order_by(ordering, Media.id).all()

    return {
        "timeBucket": f"{start.year:04d}-{start.month:02d}-01",
        "count": len(media_list),
        "id": [m.id for m in media_list],
        "ratio": [_compute_ratio(m.width, m.height) for m in media_list],
        "thumbhash": [None for _ in media_list],
        "liked": [bool(m.liked) for m in media_list],
        "createdAt": [
            m.created_at.isoformat() if m.created_at else None for m in media_list
        ],
        "thumbnailUrl": [build_thumbnail_url(m.id) for m in media_list],
    }
