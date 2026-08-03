#!/usr/bin/env python3
"""
Offline search evaluation harness - score retrieval against a labeled dataset.

Runs every query in a dataset through a retriever, then reports Precision@K,
Recall@K, MRR, empty-result rate, and per-query latency. Output is JSON so two
runs can be diffed directly.

Everything stays on this machine. Nothing uploads images, embeddings, labels,
or results, and datasets reference media by id only - never image bytes.

Retrievers:

  --stub RUN.json   Replay canned rankings. No database, no models, no photos.
                    This is what the smoke fixture and CI use.

  --api             Query a running Find instance over HTTP. Needs a live
                    stack with an indexed library. Media ids in the dataset
                    must be the media_id values that instance returns.

  --db              Retrieve straight from Postgres and rank with a Track C
                    variant (issue #99). Needs database access and real model
                    weights in this process, and pins retrieval to exact search
                    unless --approximate is passed.

Usage (from the backend directory):

    # Smoke: proves the harness itself works
    uv run python scripts/evaluate_search.py \
        --dataset tests/fixtures/search_eval/smoke_dataset_v1.json \
        --stub tests/fixtures/search_eval/smoke_run_v1.json

    # Against a live local instance
    uv run python scripts/evaluate_search.py \
        --dataset my_dataset.json --api --base-url http://localhost:8000

    # The whole Track C matrix, one retrieval per query shared by every variant
    uv run python scripts/evaluate_search.py \
        --dataset my_dataset.json --db --all-variants --out trackc.json

    # Machine-readable, for before/after comparison
    uv run python scripts/evaluate_search.py ... --json --out baseline.json

Note: results from ML_MODE=mock are meaningless as relevance measurements.
The mock embedder is unrelated to the real weighting scheme. Use mock only to
check that the plumbing runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from find_api.evaluation.dataset import (  # noqa: E402
    DatasetError,
    EvalQuery,
    load_dataset,
    load_stub_run,
)
from find_api.evaluation.runner import (  # noqa: E402
    run_dataset,
    score_outcomes,
    stub_retriever,
)
from find_api.evaluation.variants import (  # noqa: E402
    VARIANTS,
    PoolCache,
    RankingVariant,
    get_variant,
    max_pool_size,
    variant_retriever,
)


def _api_retriever(base_url: str, timeout: float, token: str | None):
    """Retriever that queries a running instance's /api/search endpoint."""
    import urllib.error
    import urllib.parse
    import urllib.request

    def _retrieve(query: EvalQuery, k: int) -> Sequence[str]:
        params = urllib.parse.urlencode({"q": query.query, "limit": k})
        url = f"{base_url.rstrip('/')}/api/search?{params}"
        request = urllib.request.Request(url)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [str(row["media_id"]) for row in payload.get("results", [])]

    return _retrieve


def _db_candidate_source(exact: bool):
    """Build a Postgres-backed candidate source using real model weights."""
    from find_api.core.database import SessionLocal
    from find_api.evaluation.sources import default_embedder, postgres_candidate_source

    return postgres_candidate_source(SessionLocal, default_embedder(), exact=exact)


def _run_variants(
    dataset,
    variants: list[RankingVariant],
    *,
    exact: bool,
    repetitions: int,
) -> dict:
    """Score several Track C variants against one shared candidate pool.

    Retrieving once and ranking many times is what makes the comparison fair:
    every variant sees byte-identical input, so a metric difference is
    attributable to the ranking rule alone. The cost is that reported latency
    covers ranking only for all but the first variant, which is recorded in the
    output rather than left for the reader to infer.
    """
    source = _db_candidate_source(exact)
    cache = PoolCache(source=source, pool_size=max_pool_size(variants, dataset.max_k))

    reports: dict[str, dict] = {}
    for variant in variants:
        retrieve = variant_retriever(variant, source, cache=cache)
        outcomes = run_dataset(dataset, retrieve, repetitions=repetitions)
        report = score_outcomes(dataset, outcomes)
        report["variant"] = {"id": variant.id, "description": variant.description}
        reports[variant.id] = report

    return {
        "result_schema_version": 1,
        "dataset_id": dataset.dataset_id,
        "retrieval": "exact" if exact else "approximate (deployed HNSW index)",
        "shared_candidate_pool": True,
        "latency_note": (
            "Candidate retrieval is shared across variants, so per-variant "
            "latency measures ranking only. Score a single variant without "
            "--all-variants for end-to-end latency."
        ),
        "variants": reports,
    }


def _print_variant_comparison(report: dict) -> None:
    print(f"Dataset       : {report['dataset_id']}")
    print(f"Retrieval     : {report['retrieval']}")
    print()

    header = (
        f"{'VARIANT':<8} {'MRR':>8} {'P@10':>8} {'R@10':>8} {'EMPTY':>8}  DESCRIPTION"
    )
    print(header)
    print("-" * len(header))
    for variant_id, row in report["variants"].items():
        metrics = row["metrics"]
        at_10 = metrics["at_k"].get("10") or next(iter(metrics["at_k"].values()))
        print(
            f"{variant_id:<8} {metrics['mrr']:>8.4f} {at_10['precision']:>8.4f} "
            f"{at_10['recall']:>8.4f} {metrics['empty_result_rate']:>8.4f}  "
            f"{row['variant']['description']}"
        )

    print()
    print(report["latency_note"])


def _print_human(report: dict) -> None:
    print(f"Dataset       : {report['dataset_id']}")
    print(f"Queries       : {report['query_count']}")
    print()

    header = f"{'K':>4}  {'PRECISION@K':>12}  {'RECALL@K':>10}"
    print(header)
    print("-" * len(header))
    for k, values in sorted(
        report["metrics"]["at_k"].items(), key=lambda kv: int(kv[0])
    ):
        print(f"{k:>4}  {values['precision']:>12.4f}  {values['recall']:>10.4f}")

    metrics = report["metrics"]
    print()
    print(f"MRR                : {metrics['mrr']:.4f}")
    print(f"Empty-result rate  : {metrics['empty_result_rate']:.4f}")
    print(f"Retriever errors   : {metrics['error_count']}")

    latency = report["latency"]
    print()
    print(
        f"Latency (ms)       : p50 {latency['p50_ms']}  p95 {latency['p95_ms']}  "
        f"p99 {latency['p99_ms']}  mean {latency['mean_ms']}"
    )

    if report["by_category"]:
        print()
        print(f"{'CATEGORY':<18} {'N':>4}  {'MRR':>8}")
        print("-" * 32)
        for name, data in report["by_category"].items():
            print(f"{name:<18} {data['count']:>4}  {data['mrr']:>8.4f}")

    if report["worst_cases"]:
        print()
        print(f"Worst cases ({len(report['worst_cases'])}):")
        for case in report["worst_cases"]:
            detail = f" [{case['error']}]" if case["error"] else ""
            print(
                f"  - {case['query_id']}: RR={case['reciprocal_rank']:.2f} "
                f"returned={case['returned']}{detail}"
            )

    if report["dataset_warnings"]:
        print()
        print("Dataset warnings:")
        for warning in report["dataset_warnings"]:
            print(f"  ! {warning}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score Find's search retrieval against a labeled dataset.",
    )
    parser.add_argument("--dataset", required=True, help="path to a dataset JSON file")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stub", metavar="RUN", help="replay canned rankings")
    source.add_argument("--api", action="store_true", help="query a live instance")
    source.add_argument(
        "--db",
        action="store_true",
        help="retrieve from Postgres and rank with a Track C variant",
    )
    parser.add_argument(
        "--variant",
        default="C0",
        help=f"Track C ranking variant for --db ({', '.join(sorted(VARIANTS))})",
    )
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="score every Track C variant against one shared candidate pool",
    )
    parser.add_argument(
        "--approximate",
        action="store_true",
        help=(
            "use the deployed HNSW index instead of pinning exact search; "
            "ranking differences then include ANN recall error"
        ),
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default=None, help="bearer token for --api")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="re-run each query and keep the median latency",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument("--out", default=None, help="also write JSON to this path")
    args = parser.parse_args(argv)

    # Checked here so a bad value produces the same "error: ..." line as every
    # other input problem, rather than a raw traceback out of run_dataset.
    if args.repetitions < 1:
        print("error: --repetitions must be at least 1", file=sys.stderr)
        return 2

    if (args.all_variants or args.approximate) and not args.db:
        print("error: --all-variants and --approximate require --db", file=sys.stderr)
        return 2

    try:
        dataset = load_dataset(args.dataset)
    except DatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    exact = not args.approximate

    if args.db and args.all_variants:
        report = _run_variants(
            dataset,
            [VARIANTS[key] for key in sorted(VARIANTS)],
            exact=exact,
            repetitions=args.repetitions,
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_variant_comparison(report)
        if args.out:
            Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
            if not args.json:
                print(f"\nWrote {args.out}")
        return 0

    try:
        if args.stub:
            retrieve = stub_retriever(load_stub_run(args.stub))
        elif args.db:
            variant = get_variant(args.variant)
            retrieve = variant_retriever(variant, _db_candidate_source(exact))
        else:
            retrieve = _api_retriever(args.base_url, args.timeout, args.token)
    except (DatasetError, KeyError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) else exc
        print(f"error: {message}", file=sys.stderr)
        return 2

    outcomes = run_dataset(dataset, retrieve, repetitions=args.repetitions)
    report = score_outcomes(dataset, outcomes)
    if args.db:
        variant = get_variant(args.variant)
        report["variant"] = {"id": variant.id, "description": variant.description}
        report["retrieval"] = "exact" if exact else "approximate (deployed HNSW index)"

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not args.json:
            print(f"\nWrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
