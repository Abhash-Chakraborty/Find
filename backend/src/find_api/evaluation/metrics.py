"""Retrieval scoring math for the offline search evaluation harness.

Pure functions over ranked id lists. Nothing here touches the database, the
models, or the network, so the scoring can be unit-tested exactly and reused
by any retriever.

Conventions, stated explicitly because they change the numbers:

- ``precision_at_k`` divides by ``k``, not by the number of results returned.
  A query that returns 3 results for k=10 is penalised for the 7 it did not
  return. This is the standard definition and it keeps runs with different
  result counts comparable.
- ``recall_at_k`` divides by the number of relevant items for that query, so a
  query with more relevant items than ``k`` cannot reach 1.0. Datasets should
  keep relevant sets smaller than the smallest ``k`` being reported, and the
  loader warns when they do not.
- Ranks are 1-based, matching how MRR is normally defined.
- Duplicate ids in a ranking are counted once, at their first position.
"""

from __future__ import annotations

from statistics import median
from typing import Iterable, Sequence


def _dedupe(ranking: Sequence[str]) -> list[str]:
    """First occurrence wins, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for item in ranking:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def precision_at_k(ranking: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the top ``k`` slots filled by a relevant item."""
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    top = _dedupe(ranking)[:k]
    hits = sum(1 for item in top if item in relevant_set)
    return hits / k


def recall_at_k(ranking: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the relevant items that appear in the top ``k``."""
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    top = _dedupe(ranking)[:k]
    hits = sum(1 for item in top if item in relevant_set)
    return hits / len(relevant_set)


def reciprocal_rank(ranking: Sequence[str], relevant: Iterable[str]) -> float:
    """``1 / rank`` of the first relevant hit, or 0.0 if there is none."""
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    for index, item in enumerate(_dedupe(ranking), start=1):
        if item in relevant_set:
            return 1.0 / index
    return 0.0


def mean_reciprocal_rank(
    rankings: Sequence[Sequence[str]], relevants: Sequence[Iterable[str]]
) -> float:
    """MRR across queries. Queries with no relevant hit contribute 0.0."""
    if len(rankings) != len(relevants):
        raise ValueError("rankings and relevants must be the same length")
    if not rankings:
        return 0.0
    total = sum(
        reciprocal_rank(ranking, relevant)
        for ranking, relevant in zip(rankings, relevants)
    )
    return total / len(rankings)


def empty_result_rate(rankings: Sequence[Sequence[str]]) -> float:
    """Fraction of queries that returned nothing at all."""
    if not rankings:
        return 0.0
    return sum(1 for ranking in rankings if len(ranking) == 0) / len(rankings)


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile.

    Deliberately not interpolated: evaluation runs are small (tens of queries),
    and an interpolated p95 over 20 samples invents a number that no query
    actually produced. Nearest-rank always returns an observed value.
    """
    if not values:
        return 0.0
    if not 0 < pct <= 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    # Nearest-rank: ceil(pct/100 * n), 1-based, clamped to the last element.
    rank = -(-int(pct * len(ordered)) // 100) or 1
    return ordered[min(rank, len(ordered)) - 1]


def latency_summary(samples: Sequence[float]) -> dict[str, float]:
    """p50/p95/p99, mean, min, and max over per-query latencies in ms."""
    if not samples:
        return {
            "count": 0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }
    return {
        "count": len(samples),
        "mean_ms": round(sum(samples) / len(samples), 2),
        "p50_ms": round(median(samples), 2),
        "p95_ms": round(percentile(samples, 95), 2),
        "p99_ms": round(percentile(samples, 99), 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
    }
