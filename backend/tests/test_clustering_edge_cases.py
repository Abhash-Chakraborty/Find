"""Backend tests for clustering edge cases."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from find_api.core.config import settings
from find_api.workers.jobs import cluster_images


def _make_media_row(media_id: int = 1, vector: list[float] | None = None):
    """Return a minimal object matching the columns `cluster_images` reads."""
    return SimpleNamespace(
        id=media_id,
        vector=vector or list(np.random.rand(settings.EMBEDDING_DIM).astype(float)),
    )


def _media_rows(count: int) -> list[SimpleNamespace]:
    return [_make_media_row(media_id=index + 1) for index in range(count)]


class TestClusteringJobEdgeCases:
    def test_zero_indexed_images_returns_early(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with (
            patch("find_api.workers.jobs.SessionLocal", return_value=mock_db),
            patch("find_api.workers.jobs.clear_clustering_job_state"),
            patch("find_api.ml.clusterer.get_image_clusterer") as mock_clusterer,
        ):
            result = cluster_images()

        mock_clusterer.assert_not_called()
        mock_db.add.assert_not_called()
        assert result["n_clusters"] == 0
        assert result["total_points"] == 0
        assert "Not enough" in result["message"]

    def test_fewer_than_min_cluster_size_skips_clusterer(self):
        if settings.MIN_CLUSTER_SIZE < 2:
            pytest.skip(
                f"Cannot test below-threshold when MIN_CLUSTER_SIZE={settings.MIN_CLUSTER_SIZE}"
            )

        count = settings.MIN_CLUSTER_SIZE - 1
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = _media_rows(
            count
        )

        with (
            patch("find_api.workers.jobs.SessionLocal", return_value=mock_db),
            patch("find_api.workers.jobs.clear_clustering_job_state"),
            patch("find_api.ml.clusterer.get_image_clusterer") as mock_clusterer,
        ):
            result = cluster_images()

        mock_clusterer.assert_not_called()
        mock_db.add.assert_not_called()
        assert result["n_clusters"] == 0
        assert result["total_points"] == count
        assert "Not enough" in result["message"]

    def test_no_stable_clusters_returns_empty_cluster_ids(self):
        images = _media_rows(settings.MIN_CLUSTER_SIZE + 5)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = images

        mock_clusterer = MagicMock()
        mock_clusterer.cluster.return_value = (
            np.full(len(images), fill_value=-1, dtype=int),
            {
                "n_clusters": 0,
                "noise_points": len(images),
                "total_points": len(images),
            },
        )

        with (
            patch("find_api.workers.jobs.SessionLocal", return_value=mock_db),
            patch("find_api.workers.jobs.clear_clustering_job_state"),
            patch(
                "find_api.ml.clusterer.get_image_clusterer",
                return_value=mock_clusterer,
            ),
        ):
            result = cluster_images()

        mock_db.add.assert_not_called()
        # No DB commit should occur when clustering finds no stable clusters
        mock_db.commit.assert_not_called()
        assert result["cluster_ids"] == []
        assert "No stable clusters" in result["message"]

    def test_successful_clustering_persists_clusters(self):
        count = settings.MIN_CLUSTER_SIZE * 4
        images = _media_rows(count)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = images

        mock_clusterer = MagicMock()
        mock_clusterer.cluster.return_value = (
            np.array([index % 2 for index in range(count)], dtype=int),
            {
                "n_clusters": 2,
                "noise_points": 0,
                "total_points": count,
            },
        )
        fake_centroid = np.zeros(settings.EMBEDDING_DIM, dtype=np.float32)
        mock_clusterer.compute_centroids.return_value = {
            0: fake_centroid,
            1: fake_centroid,
        }

        added_clusters = []

        def fake_add(cluster):
            cluster.id = len(added_clusters) + 1
            added_clusters.append(cluster)

        mock_db.add.side_effect = fake_add

        with (
            patch("find_api.workers.jobs.SessionLocal", return_value=mock_db),
            patch("find_api.workers.jobs.clear_clustering_job_state"),
            patch(
                "find_api.ml.clusterer.get_image_clusterer",
                return_value=mock_clusterer,
            ),
        ):
            result = cluster_images()

        assert mock_db.add.call_count == 2
        mock_db.commit.assert_called()
        assert result["n_clusters"] == 2
        assert len(result["cluster_ids"]) == 2
        assert "successfully" in result["message"].lower()
