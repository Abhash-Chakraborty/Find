#!/usr/bin/env python3
"""
Measure what recall Find's HNSW index configuration costs against exact search.

Track A of docs/research/search-retrieval-benchmark-plan.md. This is the one
comparison in that plan that needs no labeled data and no real photos: the
ground truth is exact nearest-neighbour search over the same vectors, not a
human judgement, so the only inputs are a corpus of vectors and an index.

Why it matters: migration `hnsw_vector_idx_001` created

    CREATE INDEX ix_media_vector_hnsw ON media USING hnsw (vector vector_cosine_ops)

with default build parameters, and `hnsw.ef_search` is never set anywhere in
the codebase. Search then does `ORDER BY vector <=> :q LIMIT :k`, which the
planner normally satisfies from that index. So Find serves approximate results
under parameters nobody chose, and the recall cost has never been measured.

WHAT THIS DOES AND DOES NOT TELL YOU

It characterises the *index configuration* - how much recall the deployed HNSW
settings lose relative to exact search, and how `ef_search` trades recall for
latency, at a given corpus size and vector distribution.

It is NOT a measurement of Find's search quality. The vectors here are
synthetic, not SigLIP embeddings. Two distributions are run because they
bracket the real case:

  clustered - points around random centres on the unit sphere. Closer to real
              image embeddings, which are strongly clustered. Optimistic.
  uniform   - points spread over the unit sphere. In high dimensions these are
              nearly equidistant, which is the hardest possible case for a
              graph index. Pessimistic; treat as a lower bound.

Real embeddings sit between the two. Deciding production settings still needs a
real indexed library - see Track A2 in the plan.

Usage (needs a pgvector database; nothing else in the stack is required):

    docker run -d --name find-eval-pg \
        -e POSTGRES_DB=find -e POSTGRES_USER=find -e POSTGRES_PASSWORD=evalonly \
        -p 127.0.0.1:55432:5432 pgvector/pgvector:0.8.4-pg16-bookworm

    uv run python scripts/benchmark_hnsw_recall.py \
        --dsn postgresql://find:evalonly@localhost:55432/find \
        --sizes 1000,10000 --json --out hnsw_recall.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from io import StringIO
from pathlib import Path

import numpy as np
import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from find_api.evaluation.metrics import recall_at_k  # noqa: E402

TABLE = "hnsw_bench"
DIM = 768  # settings.EMBEDDING_DIM - SigLIP ViT-B-16
INDEX_NAME = "ix_hnsw_bench_vector"


def _unit(rows: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return rows / norms


def make_vectors(count: int, kind: str, rng: np.random.Generator) -> np.ndarray:
    """Synthetic unit vectors. See the module docstring for why two kinds."""
    if kind == "uniform":
        return _unit(rng.standard_normal((count, DIM)))
    if kind == "clustered":
        # Roughly 40 images per cluster, which is the order of magnitude a
        # personal library shows (holidays, pets, documents, screenshots).
        centres = _unit(rng.standard_normal((max(count // 40, 8), DIM)))
        assign = rng.integers(0, len(centres), size=count)
        # Scale by 1/sqrt(DIM): a per-component sigma of s gives a noise vector
        # of norm s*sqrt(DIM), so an unscaled 0.35 would be norm ~9.7 against a
        # unit centre and swamp the cluster structure entirely - which is what
        # an earlier version of this script did, making "clustered" silently
        # identical to "uniform".
        sigma = 0.35 / np.sqrt(DIM)
        return _unit(centres[assign] + sigma * rng.standard_normal((count, DIM)))
    raise ValueError(f"unknown distribution {kind!r}")


def _vec_literal(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def load_corpus(conn, vectors: np.ndarray) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
        cur.execute(
            f"CREATE TABLE {TABLE} (id bigserial PRIMARY KEY, vector vector({DIM}))"
        )
        buffer = StringIO()
        for index, vec in enumerate(vectors, start=1):
            buffer.write(f"{index}\t{_vec_literal(vec)}\n")
        buffer.seek(0)
        cur.copy_expert(f"COPY {TABLE} (id, vector) FROM STDIN", buffer)
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{TABLE}','id'), {len(vectors)})"
        )
    conn.commit()


def build_index(conn, m: int | None, ef_construction: int | None) -> float:
    """Create the HNSW index; returns build seconds. None means pgvector default."""
    opts = ""
    if m is not None and ef_construction is not None:
        opts = f" WITH (m = {m}, ef_construction = {ef_construction})"
    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        # Identical shape to migration hnsw_vector_idx_001.
        cur.execute(
            f"CREATE INDEX {INDEX_NAME} ON {TABLE} USING hnsw (vector vector_cosine_ops){opts}"
        )
    conn.commit()
    return time.perf_counter() - started


def _search(cur, query: np.ndarray, k: int) -> tuple[list[str], float]:
    literal = _vec_literal(query)
    started = time.perf_counter()
    cur.execute(
        f"SELECT id FROM {TABLE} ORDER BY vector <=> %s::vector LIMIT %s",
        (literal, k),
    )
    rows = cur.fetchall()
    return [str(r[0]) for r in rows], (time.perf_counter() - started) * 1000


def exact_top_k(conn, queries: np.ndarray, k: int) -> list[list[str]]:
    out = []
    with conn.cursor() as cur:
        # Force a sequential scan so this is true nearest-neighbour ground truth.
        cur.execute("SET LOCAL enable_indexscan = off")
        cur.execute("SET LOCAL enable_bitmapscan = off")
        for query in queries:
            ids, _ = _search(cur, query, k)
            out.append(ids)
    conn.rollback()
    return out


def hnsw_top_k(conn, queries: np.ndarray, k: int, ef_search: int | None):
    rankings, latencies = [], []
    with conn.cursor() as cur:
        if ef_search is not None:
            cur.execute(f"SET LOCAL hnsw.ef_search = {ef_search}")
        for query in queries:
            ids, ms = _search(cur, query, k)
            rankings.append(ids)
            latencies.append(ms)
    conn.rollback()
    return rankings, latencies


def _pct(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    rank = -(-int(pct * len(ordered)) // 100) or 1
    return ordered[min(rank, len(ordered)) - 1]


def make_queries(
    corpus: np.ndarray, count: int, rng: np.random.Generator, sigma: float = 0.25
) -> np.ndarray:
    """Queries drawn *near* corpus points, which is what makes recall meaningful.

    An earlier version generated queries with a second, independent call to
    make_vectors(). Because that function picks fresh cluster centres each
    call, the queries landed nowhere near the corpus's clusters: every corpus
    point sat at roughly the same distance, the 10th and 60th neighbours
    differed by ~0.02 cosine, and recall@10 degenerated into rank agreement
    among near-ties. It reported ~0.43 recall for configurations that were in
    fact returning equally-good results.

    A real text query embeds close to the images it describes, so queries are
    now perturbations of sampled corpus vectors. That gives the top-k a genuine
    margin over the rest, which is the precondition for recall to mean anything.
    """
    picks = corpus[rng.integers(0, len(corpus), size=count)]
    return _unit(picks + (sigma / np.sqrt(DIM)) * rng.standard_normal((count, DIM)))


def neighbour_margin(conn, queries: np.ndarray, k: int) -> float:
    """Mean cosine gap between the kth and 3kth exact neighbour.

    Reported alongside recall so the number is interpretable. A margin near
    zero means the candidates around rank k are effectively tied, and recall@k
    is then measuring tie-breaking rather than retrieval quality.
    """
    gaps = []
    with conn.cursor() as cur:
        cur.execute("SET LOCAL enable_indexscan = off")
        cur.execute("SET LOCAL enable_bitmapscan = off")
        for query in queries[: min(len(queries), 25)]:
            cur.execute(
                f"SELECT vector <=> %s::vector AS d FROM {TABLE} ORDER BY d LIMIT %s",
                (_vec_literal(query), 3 * k),
            )
            distances = [float(r[0]) for r in cur.fetchall()]
            if len(distances) >= 3 * k:
                gaps.append(distances[3 * k - 1] - distances[k - 1])
    conn.rollback()
    return float(np.mean(gaps)) if gaps else 0.0


def run(conn, size: int, kind: str, k: int, n_queries: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    corpus = make_vectors(size, kind, rng)
    queries = make_queries(corpus, n_queries, rng)

    load_corpus(conn, corpus)
    truth = exact_top_k(conn, queries, k)
    margin = neighbour_margin(conn, queries, k)

    results = {
        "size": size,
        "distribution": kind,
        "k": k,
        "queries": n_queries,
        # Gap between the kth and 3kth exact neighbour. Near zero means the
        # candidates are tied and recall@k measures tie-breaking, not quality.
        "neighbour_margin": round(margin, 5),
        "configs": [],
    }

    # (m, ef_construction, [ef_search values]) - None/None is the shipped default.
    for m, efc in ((None, None), (32, 128)):
        build_s = build_index(conn, m, efc)
        label = "default" if m is None else f"m={m},ef_construction={efc}"
        for ef_search in (None, 100, 200, 400):
            rankings, latencies = hnsw_top_k(conn, queries, k, ef_search)
            recalls = [
                recall_at_k(ranking, set(expected), k)
                for ranking, expected in zip(rankings, truth)
            ]
            results["configs"].append(
                {
                    "build": label,
                    "ef_search": ef_search if ef_search is not None else "default(40)",
                    "recall_at_k": round(statistics.mean(recalls), 4),
                    "recall_min": round(min(recalls), 4),
                    "build_seconds": round(build_s, 2),
                    "p50_ms": round(_pct(latencies, 50), 3),
                    "p95_ms": round(_pct(latencies, 95), 3),
                }
            )
    return results


def _print_human(report: dict) -> None:
    for block in report["runs"]:
        print(
            f"\n{block['distribution']} corpus, n={block['size']}, "
            f"k={block['k']}, {block['queries']} queries, "
            f"neighbour margin d{3 * block['k']}-d{block['k']}="
            f"{block['neighbour_margin']:.5f}"
        )
        header = f"  {'BUILD':<26} {'EF_SEARCH':<12} {'RECALL@K':>9} {'WORST':>7} {'P50 ms':>8} {'P95 ms':>8}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for cfg in block["configs"]:
            print(
                f"  {cfg['build']:<26} {str(cfg['ef_search']):<12} "
                f"{cfg['recall_at_k']:>9.4f} {cfg['recall_min']:>7.2f} "
                f"{cfg['p50_ms']:>8.3f} {cfg['p95_ms']:>8.3f}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--sizes", default="1000,10000")
    parser.add_argument("--distributions", default="clustered,uniform")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    kinds = [d.strip() for d in args.distributions.split(",") if d.strip()]

    conn = psycopg2.connect(args.dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
            pgvector_version = cur.fetchone()[0]
            cur.execute("SHOW server_version")
            pg_version = cur.fetchone()[0]
        conn.commit()

        report = {
            "pgvector_version": pgvector_version,
            "postgres_version": pg_version,
            "dim": DIM,
            "seed": args.seed,
            "note": (
                "Synthetic vectors, not SigLIP embeddings. Characterises the index "
                "configuration, not Find's retrieval quality."
            ),
            "runs": [],
        }
        for kind in kinds:
            for size in sizes:
                report["runs"].append(
                    run(conn, size, kind, args.k, args.queries, args.seed)
                )
    finally:
        conn.close()

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
