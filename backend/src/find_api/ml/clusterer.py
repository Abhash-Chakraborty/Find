"""
Clustering using HDBSCAN
"""

import numpy as np
from sklearn.cluster import HDBSCAN
from typing import Tuple, Dict
import logging

from find_api.core.config import settings

logger = logging.getLogger(__name__)


class ImageClusterer:
    """Cluster images based on embeddings using HDBSCAN"""

    def __init__(
        self,
        min_cluster_size: int = None,
        min_samples: int = None,
    ):
        # Allow override from settings, but default to small if not set
        self.min_cluster_size = min_cluster_size or getattr(
            settings, "MIN_CLUSTER_SIZE", 2
        )
        self.min_samples = min_samples or getattr(settings, "MIN_SAMPLES", 1)

        logger.info(
            f"Initialized clusterer: min_cluster_size={self.min_cluster_size}, "
            f"min_samples={self.min_samples}"
        )

    def cluster(
        self, embeddings: np.ndarray, metric: str = "euclidean"
    ) -> Tuple[np.ndarray, Dict]:
        """
        Cluster embeddings using HDBSCAN
        """
        try:
            embeddings = np.asarray(embeddings, dtype=np.float32, order="C")

            if len(embeddings) == 0:
                return np.array([]), {"n_clusters": 0, "noise_points": 0}

            # Normalize embeddings (critical for cosine similarity / euclidean on unit sphere)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            np.divide(embeddings, norms, out=embeddings, where=norms > 0)

            if len(embeddings) < self.min_cluster_size:
                logger.warning(
                    f"Not enough samples for clustering: {len(embeddings)} < {self.min_cluster_size}"
                )
                return np.full(len(embeddings), -1), {
                    "n_clusters": 0,
                    "noise_points": len(embeddings),
                }

            cluster_labels = self._fit_predict(embeddings, metric)

            # Compute statistics
            unique_labels, label_counts = np.unique(cluster_labels, return_counts=True)
            n_clusters = int(np.count_nonzero(unique_labels != -1))
            n_noise = (
                int(label_counts[unique_labels == -1][0]) if -1 in unique_labels else 0
            )

            cluster_info = {
                "n_clusters": n_clusters,
                "noise_points": n_noise,
                "total_points": len(embeddings),
                "cluster_sizes": {},
            }

            for label, count in zip(unique_labels, label_counts):
                if label != -1:
                    cluster_info["cluster_sizes"][int(label)] = int(count)

            logger.info(
                f"Clustering complete: {n_clusters} clusters, {n_noise} noise points"
            )

            return cluster_labels, cluster_info

        except Exception as e:
            logger.error(f"Failed to cluster embeddings: {e}")
            raise

    def _fit_predict(self, embeddings: np.ndarray, metric: str) -> np.ndarray:
        backend = settings.CLUSTERING_BACKEND.lower()

        if settings.USE_GPU and backend in {"auto", "cuml"}:
            try:
                labels = self._fit_predict_cuml(embeddings, metric)
                logger.info("Clustering used cuML GPU backend")
                return labels
            except ImportError:
                if backend == "cuml":
                    raise
                logger.info("cuML is not installed; falling back to CPU HDBSCAN")
            except Exception as exc:
                if backend == "cuml":
                    raise
                logger.warning("cuML HDBSCAN failed; falling back to CPU: %s", exc)

        return self._fit_predict_sklearn(embeddings, metric)

    def _fit_predict_cuml(self, embeddings: np.ndarray, metric: str) -> np.ndarray:
        if metric != "euclidean":
            raise ValueError("cuML HDBSCAN backend currently expects euclidean metric")

        from cuml.cluster import HDBSCAN as CuHDBSCAN  # type: ignore[import-not-found]

        clusterer = CuHDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric=metric,
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(embeddings)
        if hasattr(labels, "get"):
            labels = labels.get()
        return np.asarray(labels, dtype=np.int32)

    def _fit_predict_sklearn(self, embeddings: np.ndarray, metric: str) -> np.ndarray:
        clusterer_kwargs = {
            "min_cluster_size": self.min_cluster_size,
            "min_samples": self.min_samples,
            "metric": metric,
            "cluster_selection_method": "eom",
        }
        try:
            clusterer = HDBSCAN(
                **clusterer_kwargs,
                n_jobs=settings.CLUSTERING_N_JOBS,
                copy=False,
            )
        except TypeError:
            clusterer = HDBSCAN(**clusterer_kwargs)

        return np.asarray(clusterer.fit_predict(embeddings), dtype=np.int32)

    def compute_centroids(
        self, embeddings: np.ndarray, labels: np.ndarray
    ) -> Dict[int, np.ndarray]:
        """
        Compute centroid vectors for each cluster
        """
        centroids = {}

        embeddings = np.asarray(embeddings, dtype=np.float32, order="C")
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        np.divide(embeddings, norms, out=embeddings, where=norms > 0)

        labels = np.asarray(labels, dtype=np.int32)
        valid_mask = labels != -1
        if not np.any(valid_mask):
            return centroids

        valid_labels = labels[valid_mask]
        unique_labels = np.unique(valid_labels)
        inverse = np.searchsorted(unique_labels, valid_labels)
        cluster_sums = np.zeros(
            (len(unique_labels), embeddings.shape[1]),
            dtype=np.float32,
        )
        np.add.at(cluster_sums, inverse, embeddings[valid_mask])
        counts = np.bincount(inverse, minlength=len(unique_labels)).astype(np.float32)

        centroid_matrix = cluster_sums / counts[:, None]
        norms = np.linalg.norm(centroid_matrix, axis=1, keepdims=True)
        np.divide(centroid_matrix, norms, out=centroid_matrix, where=norms > 0)

        for label, centroid in zip(unique_labels, centroid_matrix):
            centroids[int(label)] = centroid

        return centroids

    def assign_to_cluster(
        self,
        embedding: np.ndarray,
        centroids: Dict[int, np.ndarray],
        threshold: float = 0.7,
    ) -> int:
        """
        Assign a single embedding to nearest cluster
        """
        if not centroids:
            return -1

        norm = np.linalg.norm(embedding)
        if norm == 0:
            return -1
        embedding = embedding / norm

        # Find nearest centroid
        best_similarity = -1
        best_cluster = -1

        for cluster_id, centroid in centroids.items():
            # Dot product of normalized vectors = cosine similarity
            similarity = np.dot(embedding, centroid)
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster_id

        # Check threshold
        if best_similarity < threshold:
            return -1

        return best_cluster


def get_image_clusterer() -> ImageClusterer:
    """Create new clusterer instance"""
    return ImageClusterer()
