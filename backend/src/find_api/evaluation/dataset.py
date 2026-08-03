"""Versioned labeled-query dataset for offline search evaluation.

A dataset maps queries to the media that *should* come back for them. It is
plain JSON so it can be diffed, reviewed, and versioned alongside code, and it
carries no image bytes — only stable media ids the operator chose.

Format (``schema_version: 1``)::

    {
      "schema_version": 1,
      "dataset_id": "smoke-v1",
      "description": "what this set is for",
      "k_values": [5, 10],
      "queries": [
        {
          "id": "q-bicycle",
          "query": "red bicycle",
          "relevant": ["img-001", "img-004"],
          "category": "object",          // optional, for per-slice reporting
          "notes": "optional free text"
        }
      ]
    }

``dataset_id`` is recorded in every result file so a set of numbers can never
be silently compared against a different dataset revision. Bump it whenever
queries or relevance judgements change — revisions are not mergeable with
their predecessors.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class DatasetError(ValueError):
    """Raised when a dataset file is missing, malformed, or self-inconsistent."""


@dataclass(frozen=True)
class EvalQuery:
    id: str
    query: str
    relevant: tuple[str, ...]
    category: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class EvalDataset:
    dataset_id: str
    k_values: tuple[int, ...]
    queries: tuple[EvalQuery, ...]
    description: str = ""
    warnings: tuple[str, ...] = field(default=())

    @property
    def max_k(self) -> int:
        return max(self.k_values)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def parse_dataset(payload: Any, *, source: str = "<memory>") -> EvalDataset:
    """Validate a decoded dataset payload and return it as an EvalDataset.

    Every failure is a ``DatasetError`` naming the offending field, because a
    silently-accepted bad dataset produces plausible numbers that are wrong,
    which is worse than a crash.
    """
    _require(isinstance(payload, dict), f"{source}: top level must be an object")

    version = payload.get("schema_version")
    _require(
        version == SCHEMA_VERSION,
        f"{source}: unsupported schema_version {version!r}; "
        f"this build understands {SCHEMA_VERSION}",
    )

    dataset_id = payload.get("dataset_id")
    _require(
        isinstance(dataset_id, str) and dataset_id.strip(),
        f"{source}: dataset_id must be a non-empty string",
    )

    raw_k = payload.get("k_values", [10])
    _require(
        isinstance(raw_k, list) and raw_k,
        f"{source}: k_values must be a non-empty list",
    )
    for value in raw_k:
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            f"{source}: k_values entries must be positive integers, got {value!r}",
        )
    k_values = tuple(sorted(set(raw_k)))

    raw_queries = payload.get("queries")
    _require(
        isinstance(raw_queries, list) and raw_queries,
        f"{source}: queries must be a non-empty list",
    )

    seen_ids: set[str] = set()
    queries: list[EvalQuery] = []
    warnings: list[str] = []

    for index, raw in enumerate(raw_queries):
        where = f"{source}: queries[{index}]"
        _require(isinstance(raw, dict), f"{where} must be an object")

        query_id = raw.get("id")
        _require(
            isinstance(query_id, str) and query_id.strip(),
            f"{where}.id must be a non-empty string",
        )
        _require(query_id not in seen_ids, f"{where}.id duplicates {query_id!r}")
        seen_ids.add(query_id)

        text = raw.get("query")
        _require(
            isinstance(text, str) and text.strip(),
            f"{where}.query must be a non-empty string",
        )

        relevant = raw.get("relevant")
        _require(
            isinstance(relevant, list) and relevant,
            f"{where}.relevant must be a non-empty list; a query with no correct "
            "answer belongs in a negative-case set, not here",
        )
        for item in relevant:
            _require(
                isinstance(item, str) and item.strip(),
                f"{where}.relevant entries must be non-empty strings, got {item!r}",
            )
        _require(
            len(set(relevant)) == len(relevant),
            f"{where}.relevant contains duplicate ids",
        )

        # Not fatal, but recall@k is capped below 1.0 here and that silently
        # drags the aggregate down, so it must be visible.
        smallest_k = min(k_values)
        if len(relevant) > smallest_k:
            warnings.append(
                f"{where} ({query_id!r}) has {len(relevant)} relevant items but the "
                f"smallest k is {smallest_k}; recall@{smallest_k} cannot exceed "
                f"{smallest_k / len(relevant):.2f} for this query"
            )

        category = raw.get("category")
        _require(
            category is None or isinstance(category, str),
            f"{where}.category must be a string when present",
        )
        notes = raw.get("notes")
        _require(
            notes is None or isinstance(notes, str),
            f"{where}.notes must be a string when present",
        )

        queries.append(
            EvalQuery(
                id=query_id,
                query=text,
                relevant=tuple(relevant),
                category=category,
                notes=notes,
            )
        )

    description = payload.get("description", "")
    _require(isinstance(description, str), f"{source}: description must be a string")

    return EvalDataset(
        dataset_id=dataset_id,
        k_values=k_values,
        queries=tuple(queries),
        description=description,
        warnings=tuple(warnings),
    )


def load_dataset(path: str | Path) -> EvalDataset:
    """Read and validate a dataset file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise DatasetError(f"dataset not found: {file_path}")
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{file_path}: invalid JSON — {exc}") from exc
    return parse_dataset(payload, source=str(file_path))


def load_stub_run(path: str | Path) -> dict[str, list[str]]:
    """Read a canned ranking file used by the stub retriever.

    Shape: ``{"schema_version": 1, "run_id": "...", "rankings": {query_id: [id, …]}}``.
    This exists so the smoke fixture can exercise the whole harness with no
    database, no models, and no private photos.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise DatasetError(f"stub run not found: {file_path}")
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{file_path}: invalid JSON — {exc}") from exc

    _require(isinstance(payload, dict), f"{file_path}: top level must be an object")
    _require(
        payload.get("schema_version") == SCHEMA_VERSION,
        f"{file_path}: unsupported schema_version {payload.get('schema_version')!r}",
    )
    rankings = payload.get("rankings")
    _require(isinstance(rankings, dict), f"{file_path}: rankings must be an object")

    out: dict[str, list[str]] = {}
    for query_id, ranking in rankings.items():
        _require(
            isinstance(ranking, list),
            f"{file_path}: rankings[{query_id!r}] must be a list",
        )
        for item in ranking:
            _require(
                isinstance(item, str),
                f"{file_path}: rankings[{query_id!r}] entries must be strings",
            )
        out[query_id] = list(ranking)
    return out
