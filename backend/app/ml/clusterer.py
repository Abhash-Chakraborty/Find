"""
Clustering using HDBSCAN
"""
import numpy as np
from sklearn.cluster import HDBSCAN
from typing import List, Tuple, Dict
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ImageClusterer:
    """Cluster images based on embeddings using HDBSCAN"""
    
    def __init__(
        self,
        min_cluster_size: int = None,
        min_samples: int = None
    ):
        self.min_cluster_size = min_cluster_size or settings.MIN_CLUSTER_SIZE
        self.min_samples = min_samples or settings.MIN_SAMPLES
        
        logger.info(
            f"Initialized clusterer: min_cluster_size={self.min_cluster_size}, "
            f"min_samples={self.min_samples}"
        )
    
    def cluster(
        self, 
        embeddings: np.ndarray,
        metric: str = 'euclidean'
    ) -> Tuple[np.ndarray, Dict]:
        """
        Cluster embeddings using HDBSCAN
        
        Args:
            embeddings: Array of shape (n_samples, embedding_dim)
            metric: Distance metric to use
            
        Returns:
            Tuple of (cluster_labels, cluster_info)
            cluster_labels: Array of cluster IDs (-1 for noise)
            cluster_info: Dict with clustering statistics
        """
        try:
            if len(embeddings) < self.min_cluster_size:
                logger.warning(
                    f"Not enough samples for clustering: {len(embeddings)} < {self.min_cluster_size}"
                )
                return np.full(len(embeddings), -1), {"n_clusters": 0, "noise_points": len(embeddings)}
            
            # Run HDBSCAN
            clusterer = HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric=metric,
                cluster_selection_method='eom'
            )
            
            cluster_labels = clusterer.fit_predict(embeddings)
            
            # Compute statistics
            n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
            n_noise = list(cluster_labels).count(-1)
            
            cluster_info = {
                "n_clusters": n_clusters,
                "noise_points": n_noise,
                "total_points": len(embeddings),
                "cluster_sizes": {}
            }
            
            # Count members per cluster
            for label in set(cluster_labels):
                if label != -1:
                    count = list(cluster_labels).count(label)
                    cluster_info["cluster_sizes"][int(label)] = count
            
            logger.info(
                f"Clustering complete: {n_clusters} clusters, {n_noise} noise points"
            )
            
            return cluster_labels, cluster_info
        
        except Exception as e:
            logger.error(f"Failed to cluster embeddings: {e}")
            raise
    
    def compute_centroids(
        self,
        embeddings: np.ndarray,
        labels: np.ndarray
    ) -> Dict[int, np.ndarray]:
        """
        Compute centroid vectors for each cluster
        
        Args:
            embeddings: Array of embeddings
            labels: Cluster labels
            
        Returns:
            Dict mapping cluster_id -> centroid_vector
        """
        centroids = {}
        
        unique_labels = set(labels)
        for label in unique_labels:
            if label == -1:  # Skip noise
                continue
            
            # Get all embeddings in this cluster
            mask = labels == label
            cluster_embeddings = embeddings[mask]
            
            # Compute mean (centroid)
            centroid = np.mean(cluster_embeddings, axis=0)
            
            # Normalize
            centroid = centroid / np.linalg.norm(centroid)
            
            centroids[int(label)] = centroid
        
        return centroids
    
    def assign_to_cluster(
        self,
        embedding: np.ndarray,
        centroids: Dict[int, np.ndarray],
        threshold: float = 0.7
    ) -> int:
        """
        Assign a single embedding to nearest cluster
        
        Args:
            embedding: Embedding vector
            centroids: Dict of cluster centroids
            threshold: Similarity threshold for assignment
            
        Returns:
            Cluster ID or -1 if no good match
        """
        if not centroids:
            return -1
        
        # Normalize embedding
        embedding = embedding / np.linalg.norm(embedding)
        
        # Find nearest centroid
        best_similarity = -1
        best_cluster = -1
        
        for cluster_id, centroid in centroids.items():
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
