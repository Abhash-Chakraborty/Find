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
from find_api.evaluation.variants import (
    VARIANTS,
    Candidate,
    PoolCache,
    RankingVariant,
    get_variant,
    max_pool_size,
    rank,
    variant_retriever,
)

# find_api.evaluation.sources is deliberately not re-exported: it reaches for
# the database and model stack, and this package must stay importable without
# either.

__all__ = [
    "RESULT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "VARIANTS",
    "Candidate",
    "DatasetError",
    "EvalDataset",
    "EvalQuery",
    "PoolCache",
    "QueryOutcome",
    "RankingVariant",
    "get_variant",
    "load_dataset",
    "load_stub_run",
    "max_pool_size",
    "parse_dataset",
    "rank",
    "run_dataset",
    "score_outcomes",
    "stub_retriever",
    "variant_retriever",
]
