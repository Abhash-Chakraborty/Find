"""Tests for the offline search evaluation harness.

Two things are covered, because they are the two ways a harness lies:
the scoring math being subtly wrong, and a malformed dataset being accepted
and producing plausible-but-meaningless numbers.
"""

from __future__ import annotations

import json

import pytest

from find_api.evaluation.dataset import (
    SCHEMA_VERSION,
    DatasetError,
    load_dataset,
    load_stub_run,
    parse_dataset,
)
from find_api.evaluation.metrics import (
    empty_result_rate,
    latency_summary,
    mean_reciprocal_rank,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from find_api.evaluation.runner import run_dataset, score_outcomes, stub_retriever

FIXTURES = "tests/fixtures/search_eval"


def _dataset(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": "unit",
        "k_values": [5],
        "queries": [{"id": "q1", "query": "a cat", "relevant": ["m1"]}],
    }
    payload.update(overrides)
    return payload


class TestPrecisionAtK:
    def test_divides_by_k_not_by_results_returned(self):
        # Two hits in a 3-long ranking, scored at k=10, is 0.2 — not 0.667.
        # Returning fewer results than k is a failure to fill the slots.
        assert precision_at_k(["a", "b", "c"], {"a", "b"}, 10) == pytest.approx(0.2)

    def test_only_counts_the_top_k(self):
        assert precision_at_k(["x", "y", "a"], {"a"}, 2) == 0.0
        assert precision_at_k(["x", "y", "a"], {"a"}, 3) == pytest.approx(1 / 3)

    def test_duplicates_count_once_at_first_position(self):
        assert precision_at_k(["a", "a", "a"], {"a"}, 3) == pytest.approx(1 / 3)

    def test_empty_relevant_set_scores_zero(self):
        assert precision_at_k(["a"], set(), 5) == 0.0

    def test_rejects_non_positive_k(self):
        with pytest.raises(ValueError):
            precision_at_k(["a"], {"a"}, 0)


class TestRecallAtK:
    def test_divides_by_relevant_count(self):
        assert recall_at_k(["a", "b", "c"], {"a", "b"}, 10) == pytest.approx(1.0)
        assert recall_at_k(["a", "z"], {"a", "b"}, 10) == pytest.approx(0.5)

    def test_capped_by_k(self):
        # Three relevant items but only two slots: 2/3 is the ceiling.
        assert recall_at_k(["a", "b", "c"], {"a", "b", "c"}, 2) == pytest.approx(2 / 3)

    def test_duplicates_do_not_inflate(self):
        assert recall_at_k(["a", "a"], {"a", "b"}, 5) == pytest.approx(0.5)


class TestReciprocalRank:
    def test_is_one_based(self):
        assert reciprocal_rank(["a"], {"a"}) == 1.0
        assert reciprocal_rank(["x", "a"], {"a"}) == pytest.approx(0.5)
        assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_uses_first_relevant_hit(self):
        assert reciprocal_rank(["x", "a", "b"], {"a", "b"}) == pytest.approx(0.5)

    def test_no_hit_is_zero(self):
        assert reciprocal_rank(["x", "y"], {"a"}) == 0.0
        assert reciprocal_rank([], {"a"}) == 0.0

    def test_mean_counts_misses_as_zero(self):
        # (1.0 + 0.0) / 2 — a missed query must drag the mean down, not be
        # skipped, or MRR silently rewards returning nothing.
        assert mean_reciprocal_rank([["a"], ["x"]], [{"a"}, {"b"}]) == pytest.approx(
            0.5
        )

    def test_mean_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            mean_reciprocal_rank([["a"]], [{"a"}, {"b"}])


class TestEmptyResultRate:
    def test_counts_only_zero_length_rankings(self):
        assert empty_result_rate([["a"], [], ["b"], []]) == pytest.approx(0.5)
        assert empty_result_rate([["a"]]) == 0.0
        assert empty_result_rate([]) == 0.0


class TestPercentileAndLatency:
    def test_nearest_rank_returns_an_observed_value(self):
        values = [10.0, 20.0, 30.0, 40.0]
        assert percentile(values, 50) in values
        assert percentile(values, 100) == 40.0
        assert percentile(values, 1) == 10.0

    def test_rejects_out_of_range_percentile(self):
        with pytest.raises(ValueError):
            percentile([1.0], 0)
        with pytest.raises(ValueError):
            percentile([1.0], 101)

    def test_summary_of_empty_samples_is_zeroed_not_an_error(self):
        summary = latency_summary([])
        assert summary["count"] == 0
        assert summary["p95_ms"] == 0.0

    def test_summary_reports_expected_fields(self):
        summary = latency_summary([5.0, 15.0, 25.0])
        assert summary["count"] == 3
        assert summary["min_ms"] == 5.0
        assert summary["max_ms"] == 25.0
        assert summary["p50_ms"] == 15.0


class TestDatasetValidation:
    def test_accepts_a_minimal_valid_dataset(self):
        dataset = parse_dataset(_dataset())
        assert dataset.dataset_id == "unit"
        assert dataset.max_k == 5
        assert dataset.queries[0].relevant == ("m1",)

    def test_rejects_unknown_schema_version(self):
        with pytest.raises(DatasetError, match="schema_version"):
            parse_dataset(_dataset(schema_version=99))

    def test_rejects_non_object_payload(self):
        with pytest.raises(DatasetError, match="top level"):
            parse_dataset([1, 2, 3])

    def test_rejects_missing_dataset_id(self):
        payload = _dataset()
        del payload["dataset_id"]
        with pytest.raises(DatasetError, match="dataset_id"):
            parse_dataset(payload)

    def test_rejects_empty_queries(self):
        with pytest.raises(DatasetError, match="queries"):
            parse_dataset(_dataset(queries=[]))

    def test_rejects_duplicate_query_ids(self):
        with pytest.raises(DatasetError, match="duplicates"):
            parse_dataset(
                _dataset(
                    queries=[
                        {"id": "q1", "query": "a", "relevant": ["m1"]},
                        {"id": "q1", "query": "b", "relevant": ["m2"]},
                    ]
                )
            )

    def test_rejects_empty_relevant_list(self):
        with pytest.raises(DatasetError, match="relevant"):
            parse_dataset(
                _dataset(queries=[{"id": "q1", "query": "a", "relevant": []}])
            )

    def test_rejects_duplicate_relevant_ids(self):
        with pytest.raises(DatasetError, match="duplicate"):
            parse_dataset(
                _dataset(queries=[{"id": "q1", "query": "a", "relevant": ["m1", "m1"]}])
            )

    def test_rejects_blank_query_text(self):
        with pytest.raises(DatasetError, match="query"):
            parse_dataset(
                _dataset(queries=[{"id": "q1", "query": "   ", "relevant": ["m1"]}])
            )

    @pytest.mark.parametrize("bad_k", [[], [0], [-1], ["5"], [True]])
    def test_rejects_invalid_k_values(self, bad_k):
        with pytest.raises(DatasetError, match="k_values"):
            parse_dataset(_dataset(k_values=bad_k))

    def test_warns_when_relevant_set_exceeds_smallest_k(self):
        dataset = parse_dataset(
            _dataset(
                k_values=[2],
                queries=[{"id": "q1", "query": "a", "relevant": ["m1", "m2", "m3"]}],
            )
        )
        assert dataset.warnings
        assert "recall@2" in dataset.warnings[0]

    def test_missing_file_is_a_dataset_error(self, tmp_path):
        with pytest.raises(DatasetError, match="not found"):
            load_dataset(tmp_path / "nope.json")

    def test_invalid_json_is_a_dataset_error(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(DatasetError, match="invalid JSON"):
            load_dataset(bad)


class TestStubRunValidation:
    def test_rejects_wrong_schema_version(self, tmp_path):
        path = tmp_path / "run.json"
        path.write_text(json.dumps({"schema_version": 99, "rankings": {}}), "utf-8")
        with pytest.raises(DatasetError, match="schema_version"):
            load_stub_run(path)

    def test_rejects_non_list_ranking(self, tmp_path):
        path = tmp_path / "run.json"
        path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "rankings": {"q1": "m1"}}),
            "utf-8",
        )
        with pytest.raises(DatasetError, match="must be a list"):
            load_stub_run(path)


class TestRunnerScoring:
    def test_scores_the_shipped_smoke_fixture_to_known_values(self):
        dataset = load_dataset(f"{FIXTURES}/smoke_dataset_v1.json")
        rankings = load_stub_run(f"{FIXTURES}/smoke_run_v1.json")
        report = score_outcomes(dataset, run_dataset(dataset, stub_retriever(rankings)))

        # Hand-computed from the fixture; see the guide for the working.
        assert report["metrics"]["at_k"]["5"]["precision"] == pytest.approx(0.16)
        assert report["metrics"]["at_k"]["5"]["recall"] == pytest.approx(0.5)
        assert report["metrics"]["at_k"]["10"]["precision"] == pytest.approx(0.08)
        assert report["metrics"]["mrr"] == pytest.approx(0.3667, abs=1e-4)
        assert report["metrics"]["empty_result_rate"] == pytest.approx(0.2)
        assert report["metrics"]["error_count"] == 0

    def test_reports_per_category_slices(self):
        dataset = load_dataset(f"{FIXTURES}/smoke_dataset_v1.json")
        rankings = load_stub_run(f"{FIXTURES}/smoke_run_v1.json")
        report = score_outcomes(dataset, run_dataset(dataset, stub_retriever(rankings)))
        assert report["by_category"]["object"]["mrr"] == pytest.approx(1.0)
        assert report["by_category"]["hard-negative"]["mrr"] == 0.0
        assert report["by_category"]["hard-negative"]["count"] == 2

    def test_lists_misses_and_empty_responses_in_worst_cases(self):
        dataset = load_dataset(f"{FIXTURES}/smoke_dataset_v1.json")
        rankings = load_stub_run(f"{FIXTURES}/smoke_run_v1.json")
        report = score_outcomes(dataset, run_dataset(dataset, stub_retriever(rankings)))
        ids = {case["query_id"] for case in report["worst_cases"]}
        assert ids == {"q-miss-unicorn", "q-empty-response"}

    def test_result_document_is_json_serialisable(self):
        dataset = load_dataset(f"{FIXTURES}/smoke_dataset_v1.json")
        rankings = load_stub_run(f"{FIXTURES}/smoke_run_v1.json")
        report = score_outcomes(dataset, run_dataset(dataset, stub_retriever(rankings)))
        # Strict: before/after comparison depends on this being writable.
        json.dumps(report)
        assert report["dataset_id"] == "smoke-v1"
        assert report["result_schema_version"] == 1

    def test_a_failing_retriever_is_recorded_not_raised(self):
        dataset = parse_dataset(_dataset())

        def _broken(query, k):
            raise RuntimeError("retriever exploded")

        report = score_outcomes(dataset, run_dataset(dataset, _broken))
        assert report["metrics"]["error_count"] == 1
        assert report["metrics"]["empty_result_rate"] == 1.0
        assert "retriever exploded" in report["worst_cases"][0]["error"]

    def test_rejects_zero_repetitions(self):
        dataset = parse_dataset(_dataset())
        with pytest.raises(ValueError):
            run_dataset(dataset, stub_retriever({}), repetitions=0)


class TestReviewRegressions:
    """Cases for bugs found in review of the harness itself."""

    def test_p50_reports_an_observed_sample_on_even_length_input(self):
        # statistics.median() averages the two middle values, so an even-length
        # sample produced a p50 no query actually recorded — the one percentile
        # here that broke the "always an observed value" promise.
        summary = latency_summary([10.0, 20.0])
        assert summary["p50_ms"] in (10.0, 20.0)
        assert summary["p50_ms"] != 15.0

    def test_odd_length_p50_is_unchanged(self):
        assert latency_summary([5.0, 15.0, 25.0])["p50_ms"] == 15.0

    def test_a_later_repetition_failing_scores_as_a_miss(self):
        # The first attempt succeeds and the second raises. Keeping the first
        # ranking would credit precision, recall, and MRR for a query that
        # errored.
        dataset = parse_dataset(_dataset())
        calls = {"n": 0}

        def _flaky(query, k):
            calls["n"] += 1
            if calls["n"] == 1:
                return ["m1"]
            raise RuntimeError("second attempt exploded")

        report = score_outcomes(dataset, run_dataset(dataset, _flaky, repetitions=3))
        assert report["metrics"]["error_count"] == 1
        assert report["metrics"]["mrr"] == 0.0
        assert report["metrics"]["at_k"]["5"]["precision"] == 0.0
        assert report["metrics"]["at_k"]["5"]["recall"] == 0.0
        assert report["metrics"]["empty_result_rate"] == 1.0
