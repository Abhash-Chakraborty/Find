"""
Regression tests for the cluster_images() safe-mutation fix.

Core invariant being tested:
  DB destructive operations (clearing Media.cluster_id, deleting Cluster rows)
  must NEVER execute before clustering results are validated.
  On any abort path (too few images, no stable clusters, clusterer exception),
  the DB must remain completely unchanged.

All external I/O is mocked — no Postgres, Redis, MinIO, or ML GPU is needed.

Run with:
    cd backend
    python -m pytest tests/test_cluster_images_regression.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from find_api.core.config import settings

# Dimension for test embeddings — small to keep tests fast.
_DIM = 4


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_media_rows(n: int) -> list[SimpleNamespace]:
    """Return `n` fake media rows with proper list vectors."""
    rng = np.random.default_rng(0)
    return [
        SimpleNamespace(
            id=i + 1,
            vector=rng.standard_normal(_DIM).astype(float).tolist(),
        )
        for i in range(n)
    ]


def _make_mock_db(media_rows: list[SimpleNamespace]) -> MagicMock:
    """
    Build a MagicMock session whose media query returns `media_rows`.

    Call-chain mapping (mirrors jobs.py queries):
      db.query(Media.id, Media.vector).filter(...).all()  → media_rows
      db.query(Cluster).delete(...)                       → tracked
      db.query(Media).filter(...).update(...)             → tracked
      db.add(cluster)                                     → assigns cluster.id
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = media_rows

    added: list = []

    def _fake_add(obj):
        obj.id = len(added) + 1
        added.append(obj)

    mock_db.add.side_effect = _fake_add
    return mock_db


def _make_clusterer(labels: list[int], n_clusters: int | None = None) -> MagicMock:
    """Return a mock clusterer that yields the given `labels`."""
    unique = {int(lbl) for lbl in labels if int(lbl) != -1}
    n = n_clusters if n_clusters is not None else len(unique)
    info = {
        "n_clusters": n,
        "noise_points": labels.count(-1),
        "total_points": len(labels),
    }
    mock_clusterer = MagicMock()
    mock_clusterer.cluster.return_value = (np.asarray(labels, dtype=int), info)
    mock_clusterer.compute_centroids.return_value = {
        lbl: np.zeros(_DIM, dtype=np.float32) for lbl in unique
    }
    return mock_clusterer


def _run(mock_db: MagicMock, mock_clusterer: MagicMock):
    """Run cluster_images() with all external dependencies fully mocked."""
    from find_api.workers.jobs import cluster_images

    with (
        patch("find_api.workers.jobs.SessionLocal", return_value=mock_db),
        patch("find_api.workers.jobs.clear_clustering_job_state"),
        patch("find_api.workers.jobs.get_model_manager"),
        patch(
            "find_api.ml.clusterer.get_image_clusterer",
            return_value=mock_clusterer,
        ),
    ):
        return cluster_images()


def _assert_no_destructive_db_calls(mock_db: MagicMock) -> None:
    """
    Assert that neither the cluster-delete nor the cluster_id-clear was called.

    jobs.py issues:
      db.query(Cluster).delete(synchronize_session=False)          ← delete clusters
      db.query(Media).filter(...).update({cluster_id: None}, ...)  ← clear assignments
    """
    # db.query(Cluster).delete() — no filter in between
    mock_db.query.return_value.delete.assert_not_called()
    # db.query(Media).filter(...).update(...)
    mock_db.query.return_value.filter.return_value.update.assert_not_called()


# ---------------------------------------------------------------------------
# 1. Abort: too few images
# ---------------------------------------------------------------------------


class TestAbortTooFewImages:
    """cluster_images() must not touch the DB when images < MIN_CLUSTER_SIZE."""

    def test_no_destructive_calls_when_zero_images(self):
        mock_db = _make_mock_db(media_rows=[])
        clusterer = MagicMock()

        result = _run(mock_db, clusterer)

        clusterer.cluster.assert_not_called()
        mock_db.commit.assert_not_called()
        _assert_no_destructive_db_calls(mock_db)

        assert result["n_clusters"] == 0
        assert "Not enough" in result["message"]

    def test_no_destructive_calls_when_below_threshold(self):
        if settings.MIN_CLUSTER_SIZE < 2:
            pytest.skip("MIN_CLUSTER_SIZE too small to test below-threshold path")

        rows = _make_media_rows(settings.MIN_CLUSTER_SIZE - 1)
        mock_db = _make_mock_db(rows)
        clusterer = MagicMock()

        result = _run(mock_db, clusterer)

        clusterer.cluster.assert_not_called()
        mock_db.commit.assert_not_called()
        _assert_no_destructive_db_calls(mock_db)

        assert result["total_points"] == len(rows)
        assert "Not enough" in result["message"]

    def test_no_commit_on_too_few_images(self):
        """
        Regression: previously the abort path called db.commit() after clearing
        all clusters. That must never happen.
        """
        rows = _make_media_rows(max(settings.MIN_CLUSTER_SIZE - 1, 0))
        mock_db = _make_mock_db(rows)

        _run(mock_db, MagicMock())

        mock_db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Abort: no stable clusters returned by clusterer
# ---------------------------------------------------------------------------


class TestAbortNoStableClusters:
    """cluster_images() must not touch the DB when clusterer returns all noise."""

    def _enough_rows(self) -> list[SimpleNamespace]:
        return _make_media_rows(settings.MIN_CLUSTER_SIZE + 4)

    def test_no_destructive_calls_when_all_noise(self):
        rows = self._enough_rows()
        mock_db = _make_mock_db(rows)
        clusterer = _make_clusterer(labels=[-1] * len(rows))

        result = _run(mock_db, clusterer)

        clusterer.cluster.assert_called_once()
        _assert_no_destructive_db_calls(mock_db)
        mock_db.commit.assert_not_called()

        assert result["cluster_ids"] == []
        assert "No stable clusters" in result["message"]

    def test_no_commit_on_all_noise(self):
        """
        Regression: previously the abort path called db.commit() after clearing
        all clusters. The no-stable-clusters path must not commit.
        """
        rows = self._enough_rows()
        mock_db = _make_mock_db(rows)
        clusterer = _make_clusterer(labels=[-1] * len(rows))

        _run(mock_db, clusterer)

        mock_db.commit.assert_not_called()

    def test_destructive_calls_absent_even_with_many_images(self):
        rows = _make_media_rows(settings.MIN_CLUSTER_SIZE * 10)
        mock_db = _make_mock_db(rows)
        clusterer = _make_clusterer(labels=[-1] * len(rows))

        _run(mock_db, clusterer)

        _assert_no_destructive_db_calls(mock_db)


# ---------------------------------------------------------------------------
# 3. Success path: destructive ops called AFTER clustering, in one commit
# ---------------------------------------------------------------------------


class TestSuccessPath:
    """
    When clustering yields stable clusters, exactly one DB commit must
    occur, and destructive operations must run AFTER the clusterer returns.
    """

    def _run_success(self, n: int = None):
        count = n or settings.MIN_CLUSTER_SIZE * 4
        rows = _make_media_rows(count)
        mock_db = _make_mock_db(rows)

        labels = [i % 2 for i in range(count)]
        clusterer = _make_clusterer(labels, n_clusters=2)

        call_order: list[str] = []

        def track_cluster(emb):
            call_order.append("cluster")
            return clusterer.cluster.return_value

        clusterer.cluster.side_effect = track_cluster

        def track_delete(*args, **kwargs):
            call_order.append("delete")
            return MagicMock()

        mock_db.query.return_value.delete.side_effect = track_delete

        def track_update(*args, **kwargs):
            call_order.append("update")
            return MagicMock()

        mock_db.query.return_value.filter.return_value.update.side_effect = track_update

        result = _run(mock_db, clusterer)
        return result, mock_db, call_order

    def test_exactly_one_commit_on_success(self):
        _, mock_db, _ = self._run_success()
        mock_db.commit.assert_called_once()

    def test_delete_called_on_success(self):
        _, mock_db, _ = self._run_success()
        mock_db.query.return_value.delete.assert_called_once()

    def test_cluster_id_clear_called_on_success(self):
        _, mock_db, _ = self._run_success()
        mock_db.query.return_value.filter.return_value.update.assert_called()

    def test_delete_happens_AFTER_cluster_computation(self):
        """
        Key ordering guarantee: destructive ops must follow clusterer.cluster(),
        not precede it.  A failure here means the fix has regressed.
        """
        _, _, call_order = self._run_success()

        assert "cluster" in call_order, "clusterer.cluster() was never called"
        assert "delete" in call_order, "db.query(Cluster).delete() was never called"

        cluster_idx = call_order.index("cluster")
        delete_idx = call_order.index("delete")

        assert cluster_idx < delete_idx, (
            f"ORDERING REGRESSION: delete() ran at position {delete_idx} but "
            f"cluster() ran at position {cluster_idx}. "
            "Destructive DB ops must happen AFTER clustering is validated."
        )

    def test_update_happens_AFTER_cluster_computation(self):
        """Media.cluster_id clear must also follow clusterer.cluster()."""
        _, _, call_order = self._run_success()

        assert "cluster" in call_order
        assert "update" in call_order

        cluster_idx = call_order.index("cluster")
        update_idx = call_order.index("update")

        assert cluster_idx < update_idx, (
            f"ORDERING REGRESSION: cluster_id clear ran at position {update_idx} "
            f"but cluster() ran at position {cluster_idx}."
        )

    def test_result_contains_new_cluster_ids(self):
        result, _, _ = self._run_success()
        assert "successfully" in result["message"].lower()
        assert len(result["cluster_ids"]) == 2


# ---------------------------------------------------------------------------
# 4. Exception path: clusterer throws — DB must be rolled back, not committed
# ---------------------------------------------------------------------------


class TestClustererException:
    """
    If the clusterer raises mid-run, the DB must be rolled back and no
    destructive operations (which now happen AFTER clustering) should have
    occurred.
    """

    def test_rollback_called_on_clusterer_exception(self):
        rows = _make_media_rows(settings.MIN_CLUSTER_SIZE + 5)
        mock_db = _make_mock_db(rows)

        bad_clusterer = MagicMock()
        bad_clusterer.cluster.side_effect = RuntimeError("clusterer exploded")

        with pytest.raises(RuntimeError, match="clusterer exploded"):
            _run(mock_db, bad_clusterer)

        mock_db.rollback.assert_called_once()

    def test_no_commit_after_clusterer_exception(self):
        rows = _make_media_rows(settings.MIN_CLUSTER_SIZE + 5)
        mock_db = _make_mock_db(rows)

        bad_clusterer = MagicMock()
        bad_clusterer.cluster.side_effect = RuntimeError("clusterer exploded")

        with pytest.raises(RuntimeError):
            _run(mock_db, bad_clusterer)

        mock_db.commit.assert_not_called()

    def test_no_destructive_calls_after_clusterer_exception(self):
        """
        Because destructive ops now run AFTER cluster(), an exception inside
        cluster() must mean neither delete nor update were ever called.
        """
        rows = _make_media_rows(settings.MIN_CLUSTER_SIZE + 5)
        mock_db = _make_mock_db(rows)

        bad_clusterer = MagicMock()
        bad_clusterer.cluster.side_effect = RuntimeError("clusterer exploded")

        with pytest.raises(RuntimeError):
            _run(mock_db, bad_clusterer)

        _assert_no_destructive_db_calls(mock_db)
