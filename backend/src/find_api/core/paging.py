"""Page sizes shared by the person, cluster and album detail endpoints."""

from fastapi import Query

# One page fills a large screen several times over, so most groups load in a
# single request; the cap stops one request from serialising a whole library.
DETAIL_PAGE_SIZE = 200
DETAIL_PAGE_MAX = 500


def detail_skip(skip: int = Query(0, ge=0)) -> int:
    return skip


def detail_limit(
    limit: int = Query(DETAIL_PAGE_SIZE, ge=1, le=DETAIL_PAGE_MAX),
) -> int:
    return limit
