"""
Background worker jobs for image processing
"""


from PIL import Image
import io
import logging
from datetime import datetime
import numpy as np

from app.core.database import SessionLocal
from app.core.storage import get_file
from app.models.media import Media
from app.utils.exif import extract_exif_data
from app.workers.processors import extract_image_metadata, generate_hybrid_embedding

logger = logging.getLogger(__name__)


def analyze_image(media_id: int):
    """
    Main worker job to analyze an uploaded image

    Args:
        media_id: Database ID of media record
    """
    # job = get_current_job()
    db = SessionLocal()

    try:
        # Get media record
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            logger.error(f"Media {media_id} not found")
            return

        logger.info(f"Processing media {media_id}: {media.filename}")

        # Update status
        media.status = "processing"
        db.commit()

        # Download image from MinIO
        image_data = get_file(media.minio_key)
        image = Image.open(io.BytesIO(image_data))

        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Store dimensions
        media.width, media.height = image.size

        # Extract EXIF data
        try:
            exif_data = extract_exif_data(image)
            media.exif_json = exif_data
        except Exception as e:
            logger.warning(f"Failed to extract EXIF: {e}")
            media.exif_json = {}

        # Extract metadata (Objects, Caption, OCR)
        metadata = extract_image_metadata(image)

        # Generate Hybrid Embedding
        media.vector = generate_hybrid_embedding(image, metadata)

        # Store metadata
        media.metadata_json = metadata
        media.status = "indexed"
        media.processed_at = datetime.utcnow()

        db.commit()

        logger.info(f"Successfully processed media {media_id}")

        return {"media_id": media_id, "status": "success", "metadata": metadata}

    except Exception as e:
        logger.error(f"Failed to process media {media_id}: {e}")

        # Update status to failed
        if media:
            media.status = "failed"
            media.error_message = str(e)
            db.commit()

        raise

    finally:
        db.close()


def cluster_images():
    """
    Background job to cluster all indexed images
    """
    from app.ml.clusterer import get_image_clusterer
    from app.models.cluster import Cluster

    db = SessionLocal()

    try:
        logger.info("Starting clustering job...")

        # Get all indexed media with embeddings
        media_list = (
            db.query(Media)
            .filter(Media.status == "indexed", Media.vector.isnot(None))
            .all()
        )

        if len(media_list) < 5:
            logger.warning("Not enough images for clustering")
            return

        # Extract embeddings and IDs
        embeddings = np.array([m.vector for m in media_list])
        media_ids = [m.id for m in media_list]

        logger.info(f"Clustering {len(media_list)} images...")

        # Run clustering
        clusterer = get_image_clusterer()
        labels, info = clusterer.cluster(embeddings)

        # Compute centroids
        centroids = clusterer.compute_centroids(embeddings, labels)

        # Update media with cluster assignments
        for i, media in enumerate(media_list):
            cluster_id = int(labels[i])
            if cluster_id != -1:
                media.cluster_id = cluster_id

        # Create or update cluster records
        for cluster_id, centroid in centroids.items():
            # Get member IDs
            member_ids = [
                media_ids[i] for i, label in enumerate(labels) if label == cluster_id
            ]

            # Check if cluster exists
            cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

            if cluster:
                cluster.member_ids = member_ids
                cluster.member_count = len(member_ids)
                cluster.centroid_vector = centroid.tolist()
            else:
                cluster = Cluster(
                    id=cluster_id,
                    cluster_type="general",
                    member_ids=member_ids,
                    member_count=len(member_ids),
                    centroid_vector=centroid.tolist(),
                )
                db.add(cluster)

        db.commit()

        logger.info(f"Clustering complete: {info}")
        return info

    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        raise

    finally:
        db.close()
