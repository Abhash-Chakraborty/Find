"""Track C ranking variant tests (issue #99).

The load-bearing test here is `test_c0_matches_production_ranking`. Every number
the Track C results table will ever report is a delta against C0, so if C0 drifts
from what `routers/search.py` actually does, every one of those deltas is
measuring the drift instead of the variant.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import fmean

import pytest

from find_api.evaluation.dataset import EvalQuery
from find_api.evaluation.variants import (
    C0,
    C1,
    C2,
    C3,
    C4,
    C5,
    C6,
    PRODUCTION_BOOST_CAP,
    PRODUCTION_CAPTION_WEIGHT,
    PRODUCTION_OBJECT_WEIGHT,
    PRODUCTION_OCR_WEIGHT,
    PRODUCTION_TEXT_TERM_BONUS,
    VARIANTS,
    Candidate,
    PoolCache,
    get_variant,
    max_pool_size,
    rank,
    resolve_threshold,
    textual_boost,
    variant_retriever,
)
from find_api.ml.search_ranking import (
    bound_similarity,
    compute_textual_boost,
    rerank_results,
    tokenize,
)

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def make_candidate(media_id, similarity, **kwargs) -> Candidate:
    return Candidate(media_id=str(media_id), vector_similarity=similarity, **kwargs)


@pytest.fixture
def pool() -> list[Candidate]:
    """A pool with every signal the variants read, and deliberate ties."""
    return [
        make_candidate(1, 0.81, caption="a red bicycle on a wall"),
        make_candidate(2, 0.79, ocr_text="INVOICE total due", liked=True),
        make_candidate(3, 0.79, object_labels=("bicycle", "person")),
        make_candidate(4, 0.55, caption="bicycle", ranking_boost=0.30),
        make_candidate(5, 0.39, caption="a dog", created_at=NOW - timedelta(days=2)),
        make_candidate(6, 0.37, caption="red bicycle wheel", album_count=2),
        make_candidate(7, 0.20, ocr_text="receipt bicycle"),
    ]


def production_ranking(query: str, candidates, k: int, threshold: float) -> list[str]:
    """Reimplementation of routers/search.py's ranking, built from its own helpers.

    Written to follow the router's structure rather than the variant module's,
    so the two can disagree. It mirrors three behaviours precisely: the SQL
    filter and ordering (`similarity > threshold`, then
    `final_score DESC, similarity DESC, id ASC` where final_score folds in
    `ranking_boost`), the LIMIT applied *before* any boost, and the Python
    rerank that scores on raw similarity plus the textual boost.
    """
    rows = [c for c in candidates if c.vector_similarity > threshold]
    rows.sort(key=lambda c: int(c.media_id))
    rows.sort(
        key=lambda c: (c.vector_similarity + c.ranking_boost, c.vector_similarity),
        reverse=True,
    )
    rows = rows[:k]

    query_tokens = tokenize(query)
    results = []
    for row in rows:
        boost = compute_textual_boost(
            query_tokens=query_tokens,
            caption=row.caption,
            ocr_text=row.ocr_text,
            object_labels=list(row.object_labels),
        )
        results.append(
            {
                "media_id": int(row.media_id),
                "similarity": bound_similarity(row.vector_similarity + boost),
                "_vector_similarity": row.vector_similarity,
            }
        )

    rerank_results(results)
    return [str(item["media_id"]) for item in results]


@pytest.mark.parametrize(
    "query",
    [
        "red bicycle",
        "invoice",
        "bicycle receipt document",
        "dog",
        "nothing matches this at all",
    ],
)
@pytest.mark.parametrize("k", [3, 5, 10])
def test_c0_matches_production_ranking(pool, query, k):
    """C0 is the production baseline, not an approximation of it."""
    assert rank(C0, query, pool, k, now=NOW) == production_ranking(
        query, pool, k, C0.threshold
    )


def test_c0_constants_match_production():
    """C0's mirrored coefficients still equal the ones production computes with.

    `textual_boost` reimplements `compute_textual_boost` so C5/C6 can vary its
    constants. This pins the two together: a change to the production
    coefficients that skipped this module would otherwise land silently and
    rebase the whole matrix.
    """
    candidate = Candidate(
        media_id="1",
        vector_similarity=0.5,
        caption="invoice for a red bicycle",
        ocr_text="INVOICE bicycle total",
        object_labels=("bicycle", "invoice"),
    )
    tokens = tokenize("invoice bicycle")

    assert textual_boost(C0, tokens, candidate) == pytest.approx(
        compute_textual_boost(
            query_tokens=tokens,
            caption=candidate.caption,
            ocr_text=candidate.ocr_text,
            object_labels=list(candidate.object_labels),
        )
    )
    assert (
        C0.caption_weight,
        C0.ocr_weight,
        C0.object_weight,
        C0.boost_cap,
        C0.text_term_bonus,
    ) == (
        PRODUCTION_CAPTION_WEIGHT,
        PRODUCTION_OCR_WEIGHT,
        PRODUCTION_OBJECT_WEIGHT,
        PRODUCTION_BOOST_CAP,
        PRODUCTION_TEXT_TERM_BONUS,
    )


def test_boost_is_capped():
    """The cap binds before the variant's coefficients can run away."""
    candidate = Candidate(
        media_id="1",
        vector_similarity=0.5,
        ocr_text=" ".join(f"word{i}" for i in range(50)),
    )
    tokens = tokenize(" ".join(f"word{i}" for i in range(50)))
    assert textual_boost(C0, tokens, candidate) == pytest.approx(C0.boost_cap)


def test_empty_query_scores_no_boost():
    """A query that tokenizes to nothing must not earn a boost."""
    candidate = Candidate(media_id="1", vector_similarity=0.5, caption="anything")
    assert textual_boost(C0, set(), candidate) == 0.0


def test_c1_returns_results_the_threshold_discards(pool):
    """C1's whole question: what does the static 0.38 cutoff throw away?"""
    baseline = rank(C0, "bicycle", pool, 10, now=NOW)
    no_threshold = rank(C1, "bicycle", pool, 10, now=NOW)

    assert set(baseline) <= set(no_threshold)
    # 6 (0.37) and 7 (0.20) sit below the cutoff and are unreachable under C0.
    assert {"6", "7"} & set(baseline) == set()
    assert {"6", "7"} <= set(no_threshold)


def test_c1_recovers_results_when_every_candidate_is_below_threshold():
    """The failure mode C1 exists to size: a query that returns nothing at all."""
    weak = [make_candidate(i, 0.30 - i * 0.01) for i in range(1, 6)]
    assert rank(C0, "anything", weak, 5, now=NOW) == []
    assert len(rank(C1, "anything", weak, 5, now=NOW)) == 5


def test_c2_cutoff_tracks_the_pool_rather_than_a_constant():
    """The adaptive cutoff moves with the pool's own mean, unlike C0's constant.

    Note what it is *not*: an absolute cutoff comparable across pools. A flat
    pool at 0.60 gets a higher cutoff than a peaked pool whose mean is 0.46,
    because `mean + z * sigma` is anchored to the mean. The rule separates
    within a query; it does not rank queries against each other.
    """
    peaked = [make_candidate(1, 0.95)] + [make_candidate(i, 0.40) for i in range(2, 10)]
    high = [make_candidate(i, 0.90 - i * 0.01) for i in range(1, 10)]

    peaked_cut = resolve_threshold(C2, peaked)
    high_cut = resolve_threshold(C2, high)

    assert peaked_cut == pytest.approx(
        fmean(c.vector_similarity for c in peaked), abs=0.2
    )
    assert high_cut > peaked_cut > C0.threshold

    # On the peaked pool the cutoff lands between the outlier and the cluster,
    # which is the behaviour C2 exists to test.
    assert rank(C2, "q", peaked, 5, now=NOW) == ["1"]


def test_c2_keeps_nothing_when_the_pool_has_no_spread():
    """A documented sharp edge, and the reason adaptive_z is a knob to sweep.

    With zero spread the cutoff equals the common score, and the filter is
    strict, so a pool of identical scores is emptied entirely. C0 would have
    returned all of them.
    """
    flat = [make_candidate(i, 0.60) for i in range(1, 10)]

    assert resolve_threshold(C2, flat) == pytest.approx(0.60)
    assert rank(C2, "q", flat, 5, now=NOW) == []
    assert len(rank(C0, "q", flat, 5, now=NOW)) == 5


def test_c2_passes_everything_through_on_a_single_candidate():
    """One sample has no spread to derive a cutoff from."""
    single = [make_candidate(1, 0.05)]
    assert resolve_threshold(C2, single) is None
    assert rank(C2, "q", single, 5, now=NOW) == ["1"]


def test_c3_pool_lets_the_boost_rescue_a_result(pool):
    """C3's premise: a wider pool means the boost can promote, not just reorder.

    Candidate 2 is the only OCR match for "invoice" and earns both the overlap
    score and the TEXT_QUERY_TERMS bonus — but under C0 the page is cut to k
    before any of that is computed, so it never gets the chance.
    """
    # 4 carries a 0.30 ranking_boost, so it and 1 take the two-row page.
    assert rank(C0, "invoice", pool, 2, now=NOW) == ["1", "4"]

    wide = rank(C3, "invoice", pool, 2, now=NOW)
    assert wide == ["2", "1"]


def test_c4_signals_only_apply_to_c4(pool):
    """Recency, favourite, and album bonuses are inert outside C4."""
    for variant in (C0, C1, C2, C3, C5, C6):
        assert variant.liked_bonus == 0.0
        assert variant.recency_weight == 0.0
        assert variant.album_bonus == 0.0

    # 2 is liked and 3 is not, and they are tied on vector score, so the
    # favourite bonus is what separates them.
    tied = [
        make_candidate(2, 0.79, liked=True),
        make_candidate(3, 0.79),
    ]
    assert rank(C4, "q", tied, 2, now=NOW)[0] == "2"
    assert rank(C3, "q", tied, 2, now=NOW)[0] == "3"  # id-descending tiebreak


def test_c4_recency_decays_with_age():
    """A fresh item earns close to the full recency weight; an old one does not."""
    fresh = [
        make_candidate(1, 0.50, created_at=NOW),
        make_candidate(2, 0.50, created_at=NOW - timedelta(days=3650)),
    ]
    assert rank(C4, "q", fresh, 2, now=NOW) == ["1", "2"]


def test_c4_handles_naive_timestamps():
    """Postgres can hand back naive datetimes; that must not raise."""
    naive = [make_candidate(1, 0.50, created_at=datetime(2026, 8, 1))]
    assert rank(C4, "q", naive, 1, now=NOW) == ["1"]


def test_c5_drops_only_the_keyword_bonus():
    """C5 removes the flat 0.05 bump and leaves the overlap score intact."""
    candidate = Candidate(
        media_id="1", vector_similarity=0.5, ocr_text="invoice total due"
    )
    tokens = tokenize("invoice")

    with_bonus = textual_boost(C0, tokens, candidate)
    without = textual_boost(C5, tokens, candidate)

    assert with_bonus - without == pytest.approx(PRODUCTION_TEXT_TERM_BONUS)
    # The overlap component survives.
    assert without == pytest.approx(PRODUCTION_OCR_WEIGHT)


def test_c6_changes_only_the_coefficients():
    """C6 varies the boost shape and nothing else about retrieval."""
    assert C6.threshold == C0.threshold
    assert C6.pool_size == C0.pool_size
    assert C6.ocr_weight > C0.ocr_weight
    assert C6.boost_cap > C0.boost_cap


def test_ranking_boost_orders_the_pool_but_not_the_score(pool):
    """Production's asymmetry, reproduced: ranking_boost gates the page only.

    4 has a 0.30 persisted boost on a 0.55 similarity, so it outranks 5 for a
    slot — but once on the page it is scored on 0.55, not 0.85.
    """
    wide = rank(C3, "zzz", pool, 7, now=NOW)
    assert wide.index("4") > wide.index("1")
    assert wide.index("4") < wide.index("5")


def test_rank_is_deterministic_under_full_ties():
    """Identical scores must not produce run-to-run ordering noise."""
    tied = [make_candidate(i, 0.50) for i in range(1, 6)]
    first = rank(C0, "q", tied, 5, now=NOW)
    assert first == rank(C0, "q", list(reversed(tied)), 5, now=NOW)
    assert first == ["5", "4", "3", "2", "1"]


def test_non_numeric_ids_rank_deterministically():
    """Datasets may use string ids; production's int tiebreak must not crash."""
    mixed = [
        make_candidate("img-a", 0.50),
        make_candidate("img-b", 0.50),
        make_candidate(7, 0.50),
    ]
    first = rank(C0, "q", mixed, 3, now=NOW)
    assert sorted(first) == ["7", "img-a", "img-b"]
    assert first == rank(C0, "q", list(reversed(mixed)), 3, now=NOW)


def test_rank_rejects_non_positive_k(pool):
    with pytest.raises(ValueError):
        rank(C0, "q", pool, 0, now=NOW)


def test_get_variant_is_case_insensitive_and_names_alternatives():
    assert get_variant("c3") is C3
    with pytest.raises(KeyError) as excinfo:
        get_variant("C9")
    assert "C0" in excinfo.value.args[0]


def test_every_matrix_entry_is_registered():
    assert set(VARIANTS) == {"C0", "C1", "C2", "C3", "C4", "C5", "C6"}
    for key, variant in VARIANTS.items():
        assert variant.id == key
        assert variant.description


def test_max_pool_size_covers_the_widest_variant():
    """A shared pool sized for C0 would silently invalidate C3 and C4."""
    assert max_pool_size([C0, C3], 10) == 100
    assert max_pool_size([C0, C1], 10) == 10
    assert max_pool_size([C0], 250) == 250


def test_pool_cache_retrieves_once_per_query(pool):
    """One retrieval per query, shared across variants — the fairness guarantee."""
    calls: list[tuple[str, int]] = []

    def source(query_text: str, pool_size: int):
        calls.append((query_text, pool_size))
        return pool

    cache = PoolCache(source=source, pool_size=max_pool_size([C0, C3], 10))
    query = EvalQuery(id="q1", query="red bicycle", relevant=("1",))

    for variant in (C0, C3, C5):
        variant_retriever(variant, source, cache=cache, now=NOW)(query, 10)

    assert calls == [("red bicycle", 100)]


def test_pool_cache_keys_on_query_id_not_text(pool):
    """Two dataset rows sharing text stay independent rows in the results table."""
    calls: list[str] = []

    def source(query_text: str, pool_size: int):
        calls.append(query_text)
        return pool

    cache = PoolCache(source=source, pool_size=10)
    retrieve = variant_retriever(C0, source, cache=cache, now=NOW)
    retrieve(EvalQuery(id="q1", query="bicycle", relevant=("1",)), 10)
    retrieve(EvalQuery(id="q2", query="bicycle", relevant=("1",)), 10)

    assert calls == ["bicycle", "bicycle"]


def test_uncached_retriever_requests_at_least_k(pool):
    """Without a cache, the source must still be asked for enough rows."""
    requested: list[int] = []

    def source(query_text: str, pool_size: int):
        requested.append(pool_size)
        return pool

    query = EvalQuery(id="q1", query="bicycle", relevant=("1",))
    variant_retriever(C0, source, now=NOW)(query, 50)
    variant_retriever(C3, source, now=NOW)(query, 200)

    assert requested == [50, 200]
