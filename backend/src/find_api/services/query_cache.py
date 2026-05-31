"""Small process-local cache for repeated semantic search queries."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from time import monotonic
from typing import Any

CACHE_MAXSIZE = 128
CACHE_TTL_SECONDS = 300

_cache_lock = Lock()
_query_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_index_version = 0


def normalize_query(query: str, limit: int, skip: int, index_signature: str) -> str:
    normalized_query = " ".join(query.lower().split())
    return f"{index_signature}:{normalized_query}:{limit}:{skip}"


def get_cached_query(
    query: str, limit: int, skip: int, index_signature: str
) -> dict[str, Any] | None:
    normalized = normalize_query(query, limit, skip, index_signature)
    now = monotonic()

    with _cache_lock:
        entry = _query_cache.get(normalized)
        if entry is None:
            return None

        if entry["expires_at"] <= now or entry["index_version"] != _index_version:
            _query_cache.pop(normalized, None)
            return None

        _query_cache.move_to_end(normalized)
        return {
            "embedding": deepcopy(entry["embedding"]),
            "response": deepcopy(entry["response"]),
        }


def set_cached_query(
    query: str,
    limit: int,
    skip: int,
    index_signature: str,
    embedding: list[float],
    response: dict[str, Any],
) -> None:
    normalized = normalize_query(query, limit, skip, index_signature)

    with _cache_lock:
        _query_cache[normalized] = {
            "embedding": deepcopy(embedding),
            "response": deepcopy(response),
            "index_version": _index_version,
            "expires_at": monotonic() + CACHE_TTL_SECONDS,
        }
        _query_cache.move_to_end(normalized)

        while len(_query_cache) > CACHE_MAXSIZE:
            _query_cache.popitem(last=False)


def invalidate_query_cache() -> None:
    global _index_version

    with _cache_lock:
        _index_version += 1
        _query_cache.clear()


def clear_query_cache() -> None:
    global _index_version

    with _cache_lock:
        _index_version = 0
        _query_cache.clear()
