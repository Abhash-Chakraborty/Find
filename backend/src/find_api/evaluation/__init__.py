"""Offline search evaluation harness.

Local-only, by construction: nothing here uploads images, embeddings, labels,
or results. Datasets carry media ids the operator chose, never image bytes.

See ``docs/guides/search-evaluation.md`` for dataset authoring guidance and
``backend/scripts/evaluate_search.py`` for the command-line entry point.
"""

from find_api.evaluation.dataset import (
    SCHEMA_VERSION,
    DatasetError,
    EvalDataset,
    EvalQuery,
    load_dataset,
    load_stub_run,
    parse_dataset,
)
from find_api.evaluation.runner import (
    RESULT_SCHEMA_VERSION,
    QueryOutcome,
    run_dataset,
    score_outcomes,
    stub_retriever,
)

__all__ = [
    "RESULT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "DatasetError",
    "EvalDataset",
    "EvalQuery",
    "QueryOutcome",
    "load_dataset",
    "load_stub_run",
    "parse_dataset",
    "run_dataset",
    "score_outcomes",
    "stub_retriever",
]
