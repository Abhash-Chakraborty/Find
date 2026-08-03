"""Track C query-side ranking variants for the search benchmark (issue #99).

`docs/research/search-retrieval-benchmark-plan.md` defines a matrix of ranking
candidates C0-C6. All of them are *query-side only*: they change how an already
retrieved candidate set is thresholded, pooled, and reranked, and none of them
touch stored vectors. That is why Track C runs before the embedding tracks —
every variant here is revertible by reverting code, with no reindex.

The split in this module exists so the comparison is fair:

- A **candidate source** does the expensive, environment-dependent part once per
  query: embed the text, hit Postgres, return a pool of `Candidate` rows with
  every signal a variant might want.
- A **variant** is pure Python over that pool.

Because the pool is retrieved once and shared, two variants scored in the same
run see byte-identical input, so any difference in their metrics is attributable
to the ranking rule and nothing else. It is also the only affordable shape: the
matrix is seven variants, and re-embedding every query seven times would
dominate the run.

`C0` is the production baseline and is asserted against the real
`find_api.ml.search_ranking` helpers in `tests/test_search_variants.py`. That
test is the point of the whole module — a baseline that has quietly drifted from
production turns every delta in the results table into a fiction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from statistics import fmean, pstdev
from typing import Callable, Sequence

from find_api.evaluation.dataset import EvalQuery
from find_api.ml.search_ranking import TEXT_QUERY_TERMS, tokenize

# Production's full-mode cutoff, mirrored from routers/search.py. Duplicated
# rather than imported because importing the router drags in the database,
# storage, and settings stack, and the harness must run without them.
PRODUCTION_THRESHOLD = 0.38

# Production coefficients, mirrored from ml/search_ranking.py for the same
# reason. `test_search_variants.py` asserts these still match.
PRODUCTION_CAPTION_WEIGHT = 0.015
PRODUCTION_OCR_WEIGHT = 0.035
PRODUCTION_OBJECT_WEIGHT = 0.010
PRODUCTION_BOOST_CAP = 0.25
PRODUCTION_TEXT_TERM_BONUS = 0.05


@dataclass(frozen=True)
class Candidate:
    """One retrieved row, with every signal any Track C variant may read.

    Populated once per query by a candidate source. Fields a given variant
    ignores simply cost nothing.
    """

    media_id: str
    vector_similarity: float
    caption: str = ""
    ocr_text: str = ""
    object_labels: tuple[str, ...] = ()
    # Persisted feedback boost. Production adds it to the SQL ordering key but
    # not to the Python score; see `_pool_sort_key`.
    ranking_boost: float = 0.0
    liked: bool = False
    created_at: datetime | None = None
    album_count: int = 0


@dataclass(frozen=True)
class RankingVariant:
    """A point in the Track C matrix.

    Defaults reproduce production exactly, so each variant below is defined by
    the one knob it changes. That is deliberate: a variant that differs from the
    baseline in two ways cannot have its effect attributed.
    """

    id: str
    description: str

    # Retrieval shape. `pool_size=None` means "pool is exactly k", which is what
    # production does — it applies the textual boost only to the page it already
    # truncated to. C3 challenges precisely that.
    pool_size: int | None = None

    # Thresholding. `threshold=None` disables the cutoff (C1). `adaptive_z`
    # switches to a per-query cutoff derived from the pool's score spread (C2).
    threshold: float | None = PRODUCTION_THRESHOLD
    adaptive_z: float | None = None

    # Boost shape (C5, C6).
    caption_weight: float = PRODUCTION_CAPTION_WEIGHT
    ocr_weight: float = PRODUCTION_OCR_WEIGHT
    object_weight: float = PRODUCTION_OBJECT_WEIGHT
    boost_cap: float = PRODUCTION_BOOST_CAP
    text_term_bonus: float = PRODUCTION_TEXT_TERM_BONUS

    # Non-semantic signals (C4). Zero everywhere else, so they contribute
    # nothing unless a variant opts in.
    liked_bonus: float = 0.0
    recency_weight: float = 0.0
    recency_half_life_days: float = 365.0
    album_bonus: float = 0.0

    def with_id(self, variant_id: str, description: str, **changes) -> RankingVariant:
        """Derive a sibling variant. Used to build sweeps of one coefficient."""
        return replace(self, id=variant_id, description=description, **changes)


def textual_boost(
    variant: RankingVariant, query_tokens: set[str], candidate: Candidate
) -> float:
    """Metadata boost under `variant`'s coefficients.

    With production coefficients this is `search_ranking.compute_textual_boost`;
    it is reimplemented rather than called because the whole point of C5/C6 is
    to vary the constants that function hardcodes.
    """
    if not query_tokens:
        return 0.0

    caption_tokens = tokenize(candidate.caption)
    ocr_tokens = tokenize(candidate.ocr_text)
    object_tokens = tokenize(" ".join(candidate.object_labels))

    boost = (
        len(query_tokens & caption_tokens) * variant.caption_weight
        + len(query_tokens & ocr_tokens) * variant.ocr_weight
        + len(query_tokens & object_tokens) * variant.object_weight
    )

    if variant.text_term_bonus and query_tokens & TEXT_QUERY_TERMS and ocr_tokens:
        boost += variant.text_term_bonus

    return min(boost, variant.boost_cap)


def metadata_boost(
    variant: RankingVariant, candidate: Candidate, now: datetime
) -> float:
    """Non-semantic boost from recency, favourites, and album membership (C4).

    Zero unless a variant opts in, so it costs the other variants nothing.
    """
    boost = 0.0

    if variant.liked_bonus and candidate.liked:
        boost += variant.liked_bonus

    if variant.album_bonus and candidate.album_count > 0:
        boost += variant.album_bonus

    if variant.recency_weight and candidate.created_at is not None:
        created = candidate.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max((now - created).total_seconds() / 86400.0, 0.0)
        # Exponential decay, so a fresh item gets the full weight and the bonus
        # tends to zero rather than going negative for old media. A linear decay
        # would need an arbitrary cutoff age.
        decay = math.exp(-math.log(2) * age_days / variant.recency_half_life_days)
        boost += variant.recency_weight * decay

    return boost


def resolve_threshold(
    variant: RankingVariant, candidates: Sequence[Candidate]
) -> float | None:
    """The similarity cutoff this variant applies to this pool.

    Returns None when nothing should be filtered. The adaptive rule (C2) is
    `mean + z * stdev` over the pool's similarities: on a query with a clear
    winner the spread is wide and the cutoff rises, and on a flat pool where
    nothing stands out it collapses toward the mean. It is one concrete rule
    the benchmark is meant to *test*, not an established one — `adaptive_z` is
    the knob to sweep.
    """
    if variant.adaptive_z is None:
        return variant.threshold

    sims = [c.vector_similarity for c in candidates]
    if len(sims) < 2:
        # Nothing to derive a spread from; filtering on a single sample would
        # be arbitrary, so pass everything through.
        return None
    return fmean(sims) + variant.adaptive_z * pstdev(sims)


def _id_sort_key(media_id: str) -> tuple[int, int, str]:
    """Deterministic descending tiebreak on id.

    Production tiebreaks on `int(media_id)` because its ids are integers.
    Datasets may use non-numeric ids, so numeric ids sort numerically (matching
    production) and others fall back to string order, with numerics ordered
    after strings under the descending sort so the two never interleave
    arbitrarily.
    """
    try:
        return (1, int(media_id), "")
    except (TypeError, ValueError):
        return (0, 0, media_id)


def _pool_sort_key(candidate: Candidate) -> tuple:
    """Production's SQL ordering: final_score DESC, similarity DESC, id ASC.

    `ranking_boost` participates here and nowhere else, exactly as in
    `routers/search.py` — the persisted feedback boost decides *which* rows
    reach the page, then the Python rerank scores them on the raw vector
    similarity plus the textual boost. Reproducing that asymmetry matters:
    folding `ranking_boost` into the final score would make C0 outrank
    production on feedback-heavy libraries and quietly flatter every variant
    measured against it.
    """
    numeric, value, text = _id_sort_key(candidate.media_id)
    return (
        candidate.vector_similarity + candidate.ranking_boost,
        candidate.vector_similarity,
        # Negated to give ascending id under a descending sort.
        -numeric,
        -value,
        text,
    )


def rank(
    variant: RankingVariant,
    query_text: str,
    candidates: Sequence[Candidate],
    k: int,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Apply `variant` to a candidate pool and return the top-k media ids."""
    if k < 1:
        raise ValueError("k must be at least 1")

    now = now or datetime.now(timezone.utc)
    query_tokens = tokenize(query_text)

    threshold = resolve_threshold(variant, candidates)
    kept = (
        list(candidates)
        if threshold is None
        else [c for c in candidates if c.vector_similarity > threshold]
    )

    # Truncate to the pool before reranking. For C0 the pool is k, which is
    # what makes it the honest baseline: production reranks only the page it
    # already cut to, so its boost can reorder but never rescue a result the
    # vector score pushed off the page.
    pool_size = variant.pool_size if variant.pool_size is not None else k
    kept.sort(key=_pool_sort_key, reverse=True)
    kept = kept[:pool_size]

    scored: list[tuple[float, float, tuple[int, int, str], str]] = []
    for candidate in kept:
        score = (
            candidate.vector_similarity
            + textual_boost(variant, query_tokens, candidate)
            + metadata_boost(variant, candidate, now)
        )
        # Production clamps the exposed score to [0, 1]. Kept because a clamp
        # creates ties at the ceiling, and ties change ordering.
        score = max(0.0, min(score, 1.0))
        scored.append(
            (
                score,
                candidate.vector_similarity,
                _id_sort_key(candidate.media_id),
                candidate.media_id,
            )
        )

    scored.sort(key=lambda row: row[:3], reverse=True)
    return [row[3] for row in scored[:k]]


# --- The matrix -------------------------------------------------------------
#
# Ids and questions come straight from the Track C table in
# docs/research/search-retrieval-benchmark-plan.md.

C0 = RankingVariant(
    id="C0",
    description="Production baseline: static 0.38 threshold, pool=k, overlap boost",
)

C1 = C0.with_id(
    "C1",
    "No threshold — how many valid results does the static cutoff discard?",
    threshold=None,
)

C2 = C0.with_id(
    "C2",
    "Adaptive threshold from the per-query score spread (mean + 0.5 sigma)",
    adaptive_z=0.5,
)

C3 = C0.with_id(
    "C3",
    "Wider candidate pool (k=100), then metadata rerank down to k",
    pool_size=100,
)

C4 = C3.with_id(
    "C4",
    "C3 plus recency, favourite, and album signals",
    liked_bonus=0.02,
    recency_weight=0.02,
    album_bonus=0.01,
)

C5 = C0.with_id(
    "C5",
    "Drop the hardcoded TEXT_QUERY_TERMS bonus — is the flat 0.05 earning its place?",
    text_term_bonus=0.0,
)

C6 = C0.with_id(
    "C6",
    "Reweight the per-signal boost coefficients and raise the cap",
    caption_weight=0.030,
    ocr_weight=0.050,
    object_weight=0.020,
    boost_cap=0.35,
)

VARIANTS: dict[str, RankingVariant] = {v.id: v for v in (C0, C1, C2, C3, C4, C5, C6)}


def get_variant(variant_id: str) -> RankingVariant:
    """Look up a variant by id, case-insensitively."""
    try:
        return VARIANTS[variant_id.strip().upper()]
    except KeyError:
        known = ", ".join(sorted(VARIANTS))
        raise KeyError(
            f"unknown variant {variant_id!r}; known variants: {known}"
        ) from None


# --- Wiring into the harness ------------------------------------------------

CandidateSource = Callable[[str, int], Sequence[Candidate]]


@dataclass
class PoolCache:
    """Per-query candidate pools, so one retrieval serves every variant.

    Keyed by query id rather than query text: two dataset entries with the same
    text are still distinct rows in the results table, and sharing a pool
    between them would make their latencies indistinguishable.
    """

    source: CandidateSource
    pool_size: int
    pools: dict[str, Sequence[Candidate]] = field(default_factory=dict)

    def get(self, query: EvalQuery) -> Sequence[Candidate]:
        if query.id not in self.pools:
            self.pools[query.id] = self.source(query.query, self.pool_size)
        return self.pools[query.id]


def variant_retriever(
    variant: RankingVariant,
    source: CandidateSource,
    *,
    cache: PoolCache | None = None,
    now: datetime | None = None,
) -> Callable[[EvalQuery, int], Sequence[str]]:
    """Adapt a variant plus a candidate source into a harness retriever.

    Pass a shared `cache` when scoring several variants in one run so the pool
    is retrieved once. Note what that does to the latency column: cached runs
    time the ranking rule only, not retrieval. Score a variant without a cache
    when its end-to-end latency is the number being reported.
    """

    def _retrieve(query: EvalQuery, k: int) -> Sequence[str]:
        if cache is not None:
            candidates = cache.get(query)
        else:
            candidates = source(query.query, max(variant.pool_size or k, k))
        return rank(variant, query.query, candidates, k, now=now)

    return _retrieve


def max_pool_size(variants: Sequence[RankingVariant], k: int) -> int:
    """Pool size that satisfies every variant in a shared-cache run.

    A shared pool has to be as large as the widest variant needs, or C3/C4 would
    silently be scored on C0's narrow pool and their whole premise would go
    untested.
    """
    return max([k] + [v.pool_size for v in variants if v.pool_size is not None])
