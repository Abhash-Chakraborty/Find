"""Tests for the HNSW recall benchmark's vector generation.

The database half needs a live pgvector instance and is exercised by running
the script; what is worth pinning here is the synthetic corpus, because a
generator that silently fails to cluster makes the "clustered vs uniform"
comparison meaningless while still producing confident-looking numbers. That
happened during development: an unscaled per-component sigma of 0.35 gives a
noise vector of norm ~9.7 in 768 dimensions, which buried a unit-norm centre
and made both distributions identical.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_hnsw_recall.py"


def _load():
    spec = importlib.util.spec_from_file_location("_hnsw_bench", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bench():
    return _load()


class TestVectorGeneration:
    def test_vectors_are_unit_norm(self, bench):
        rng = np.random.default_rng(7)
        for kind in ("clustered", "uniform"):
            vectors = bench.make_vectors(64, kind, rng)
            norms = np.linalg.norm(vectors, axis=1)
            assert np.allclose(norms, 1.0, atol=1e-6), kind

    def test_shape_matches_embedding_dim(self, bench):
        rng = np.random.default_rng(7)
        assert bench.make_vectors(12, "uniform", rng).shape == (12, bench.DIM)

    def test_clustered_actually_clusters(self, bench):
        """Intra-cluster similarity must dominate inter-cluster similarity.

        This is the assertion that would have caught the sigma bug.
        """
        rng = np.random.default_rng(11)
        centres = bench._unit(rng.standard_normal((4, bench.DIM)))
        sigma = 0.35 / np.sqrt(bench.DIM)
        groups = [
            bench._unit(centre + sigma * rng.standard_normal((40, bench.DIM)))
            for centre in centres
        ]
        intra = np.mean([g @ g.T for g in groups])
        inter = np.mean(groups[0] @ groups[1].T)
        assert intra > 0.5, f"clusters are not tight enough: intra={intra:.3f}"
        assert inter < 0.2, f"clusters are not separated: inter={inter:.3f}"

    def test_uniform_is_not_clustered(self, bench):
        rng = np.random.default_rng(13)
        vectors = bench.make_vectors(200, "uniform", rng)
        sims = vectors @ vectors.T
        np.fill_diagonal(sims, 0.0)
        # Random directions in 768 dimensions are near-orthogonal.
        assert abs(float(sims.mean())) < 0.05

    def test_rejects_unknown_distribution(self, bench):
        rng = np.random.default_rng(3)
        with pytest.raises(ValueError, match="unknown distribution"):
            bench.make_vectors(4, "gaussian-blobs", rng)

    def test_generation_is_reproducible_for_a_seed(self, bench):
        a = bench.make_vectors(16, "clustered", np.random.default_rng(99))
        b = bench.make_vectors(16, "clustered", np.random.default_rng(99))
        assert np.array_equal(a, b)


class TestVectorLiteral:
    def test_formats_as_pgvector_literal(self, bench):
        literal = bench._vec_literal(np.array([1.0, -0.5, 0.25]))
        assert literal.startswith("[") and literal.endswith("]")
        assert literal == "[1.000000,-0.500000,0.250000]"


class TestPercentile:
    def test_nearest_rank_returns_observed_values(self, bench):
        values = [1.0, 2.0, 3.0, 4.0]
        assert bench._pct(values, 100) == 4.0
        assert bench._pct(values, 50) in values


class TestQueryGeneration:
    """Queries must land near the corpus, or recall@k measures nothing.

    The first version of this benchmark generated queries with a second,
    independent make_vectors() call. That picks fresh cluster centres, so the
    queries sat far from every corpus cluster, all candidates were roughly
    equidistant, and recall@10 collapsed to ~0.43 for configurations that were
    in fact returning equally-good results.
    """

    def test_queries_are_close_to_corpus_points(self, bench):
        rng = np.random.default_rng(21)
        corpus = bench.make_vectors(500, "clustered", rng)
        queries = bench.make_queries(corpus, 50, rng)

        best = (queries @ corpus.T).max(axis=1)
        assert best.min() > 0.8, (
            f"queries drifted from the corpus: worst best-match cos sim {best.min():.3f}"
        )

    def test_independent_generation_would_not_be_close(self, bench):
        """Pins the failure mode the fix addresses."""
        rng = np.random.default_rng(21)
        corpus = bench.make_vectors(500, "clustered", rng)
        detached = bench.make_vectors(50, "clustered", rng)

        near = (bench.make_queries(corpus, 50, rng) @ corpus.T).max(axis=1).mean()
        far = (detached @ corpus.T).max(axis=1).mean()
        assert near > far + 0.3, f"near={near:.3f} far={far:.3f}"

    def test_queries_are_unit_norm(self, bench):
        rng = np.random.default_rng(5)
        corpus = bench.make_vectors(100, "uniform", rng)
        queries = bench.make_queries(corpus, 20, rng)
        assert np.allclose(np.linalg.norm(queries, axis=1), 1.0, atol=1e-6)

    def test_larger_sigma_moves_queries_further(self, bench):
        rng = np.random.default_rng(31)
        corpus = bench.make_vectors(300, "clustered", rng)
        tight = (bench.make_queries(corpus, 40, rng, sigma=0.1) @ corpus.T).max(axis=1)
        loose = (bench.make_queries(corpus, 40, rng, sigma=2.0) @ corpus.T).max(axis=1)
        assert tight.mean() > loose.mean()
