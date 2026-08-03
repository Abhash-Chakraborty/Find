"""Run a labeled dataset against a retriever and score the result.

The retriever is injected, which is the whole point of the split: the scoring
path is identical whether the rankings came from a canned fixture, a live
search endpoint, or a future experimental branch. Only then are two runs
actually comparable.

A retriever is any callable ``(EvalQuery, k) -> Sequence[str]`` returning
ranked media ids, most relevant first. It receives the whole query object, not
just the text, so a retriever can key off the query id (as the stub does) or
off ``category`` without a second lookup.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from find_api.evaluation.dataset import EvalDataset, EvalQuery
from find_api.evaluation.metrics import (
    empty_result_rate,
    latency_summary,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

Retriever = Callable[[EvalQuery, int], Sequence[str]]

RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class QueryOutcome:
    query: EvalQuery
    ranking: tuple[str, ...]
    latency_ms: float
    error: str | None = None


def stub_retriever(
    rankings: Mapping[str, Sequence[str]],
) -> Callable[[EvalQuery, int], Sequence[str]]:
    """Retriever backed by canned rankings keyed by query id.

    Used by the smoke fixture so the harness is exercised end to end with no
    database, no model weights, and no private media.
    """

    def _retrieve(query: EvalQuery, k: int) -> Sequence[str]:
        return list(rankings.get(query.id, []))[:k]

    return _retrieve


def run_dataset(
    dataset: EvalDataset,
    retrieve: Callable[[EvalQuery, int], Sequence[str]],
    *,
    repetitions: int = 1,
) -> list[QueryOutcome]:
    """Execute every query, timing each call.

    ``repetitions`` re-runs each query and keeps the median latency; rankings
    are taken from the first run. Retrieval is expected to be deterministic,
    so repeating it only sharpens the timing, never the relevance.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")

    k = dataset.max_k
    outcomes: list[QueryOutcome] = []

    for query in dataset.queries:
        samples: list[float] = []
        ranking: Sequence[str] = []
        error: str | None = None

        for attempt in range(repetitions):
            started = time.perf_counter()
            try:
                result = retrieve(query, k)
            except Exception as exc:  # noqa: BLE001 — one bad query must not
                # abort the run; it is recorded and scored as a miss.
                error = f"{type(exc).__name__}: {exc}"
                result = []
            samples.append((time.perf_counter() - started) * 1000)
            if attempt == 0:
                ranking = result
            if error:
                # Discard any ranking an earlier repetition produced. A query
                # that failed on some attempts must score as a miss, not keep
                # credit for precision, recall, and MRR from a lucky first run.
                ranking = []
                break

        samples.sort()
        outcomes.append(
            QueryOutcome(
                query=query,
                ranking=tuple(ranking),
                latency_ms=samples[len(samples) // 2],
                error=error,
            )
        )

    return outcomes


def score_outcomes(
    dataset: EvalDataset, outcomes: Sequence[QueryOutcome]
) -> dict[str, Any]:
    """Aggregate outcomes into a machine-readable result document."""
    rankings = [list(o.ranking) for o in outcomes]
    relevants = [list(o.query.relevant) for o in outcomes]

    per_k: dict[str, dict[str, float]] = {}
    for k in dataset.k_values:
        precisions = [precision_at_k(o.ranking, o.query.relevant, k) for o in outcomes]
        recalls = [recall_at_k(o.ranking, o.query.relevant, k) for o in outcomes]
        per_k[str(k)] = {
            "precision": round(sum(precisions) / len(precisions), 4)
            if precisions
            else 0.0,
            "recall": round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        }

    # Per-category slices, because an aggregate hides a category that collapsed.
    by_category: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        key = outcome.query.category or "uncategorized"
        by_category.setdefault(key, {"count": 0, "reciprocal_ranks": []})
        by_category[key]["count"] += 1
        by_category[key]["reciprocal_ranks"].append(
            reciprocal_rank(outcome.ranking, outcome.query.relevant)
        )
    category_summary = {
        name: {
            "count": data["count"],
            "mrr": round(sum(data["reciprocal_ranks"]) / data["count"], 4),
        }
        for name, data in sorted(by_category.items())
    }

    failures = [
        {
            "query_id": o.query.id,
            "query": o.query.query,
            "category": o.query.category,
            "reciprocal_rank": round(reciprocal_rank(o.ranking, o.query.relevant), 4),
            "returned": len(o.ranking),
            "error": o.error,
        }
        for o in outcomes
        if reciprocal_rank(o.ranking, o.query.relevant) == 0.0 or o.error
    ]

    return {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "dataset_id": dataset.dataset_id,
        "query_count": len(outcomes),
        "k_values": list(dataset.k_values),
        "metrics": {
            "at_k": per_k,
            "mrr": round(mean_reciprocal_rank(rankings, relevants), 4),
            "empty_result_rate": round(empty_result_rate(rankings), 4),
            "error_count": sum(1 for o in outcomes if o.error),
        },
        "latency": latency_summary([o.latency_ms for o in outcomes]),
        "by_category": category_summary,
        # Worst cases are a required output, not a footnote: a variant that
        # lifts the mean while destroying one query class is worse for users
        # than its average suggests.
        "worst_cases": sorted(failures, key=lambda f: f["query_id"]),
        "dataset_warnings": list(dataset.warnings),
    }
