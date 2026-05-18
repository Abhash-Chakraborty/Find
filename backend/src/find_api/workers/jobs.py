"""
Background worker jobs for image processing
"""

from PIL import Image
import io
import logging
from datetime import datetime

import numpy as np

from redis import Redis
from rq.job import Job

from find_api.core.config import settings
from find_api.core.database import SessionLocal
from find_api.core.queue import (
    clear_clustering_job_state,
    enqueue_clustering_job,
)
from find_api.core.storage import get_file
from find_api.models.media import Media
from find_api.utils.exif import extract_exif_data

logger = logging.getLogger(__name__)

redis_conn = Redis.from_url(settings.REDIS_URL)


def analyze_image(media_id: int):
    """
    Main worker job to analyze an uploaded image
    """

    from find_api.workers.processors import (
        extract_image_metadata,
        generate_hybrid_embedding,
    )

    db = SessionLocal()

    media = None

    try:
        media = db.query(Media).filter(Media.id == media_id).first()

        if not media:
            logger.error(f"Media {media_id} not found")
            return

        logger.info(f"Processing media {media_id}: {media.filename}")

        media.status = "processing"

        db.commit()

        image_data = get_file(media.minio_key)

        image = Image.open(io.BytesIO(image_data))

        if image.mode != "RGB":
            image = image.convert("RGB")

        media.width, media.height = image.size

        try:
            exif_data = extract_exif_data(image)
            media.exif_json = exif_data

        except Exception as e:
            logger.warning(f"Failed to extract EXIF: {e}")
            media.exif_json = {}

        metadata = extract_image_metadata(image)

        media.vector = generate_hybrid_embedding(image, metadata)

        media.metadata_json = metadata

        media.status = "indexed"

        media.processed_at = datetime.utcnow()

        media.error_message = None

        db.commit()

        try:
            enqueue_clustering_job(reason=f"media:{media_id}")

        except Exception as exc:
            logger.warning(
                "Indexed media %s but failed to queue clustering: %s",
                media_id,
                exc,
            )

        logger.info(f"Successfully processed media {media_id}")

        return {
            "media_id": media_id,
            "status": "success",
            "metadata": metadata,
        }

    except Exception as e:
        logger.error(f"Failed to process media {media_id}: {e}")

        db.rollback()

        if media:
            media.status = "failed"

            media.error_message = str(e)

            db.commit()

        raise

    finally:
        db.close()


def reconcile_stale_jobs():
    """
    Reconcile media rows stuck in processing state.

    If the linked RQ job:
    - no longer exists
    - failed
    - stopped unexpectedly

    then mark media as failed.
    """

    db = SessionLocal()

    try:
        processing_media = (
            db.query(Media)
            .filter(Media.status == "processing")
            .all()
        )

        reconciled = 0

        for media in processing_media:

            if not media.analysis_job_id:
                logger.warning(
                    "Media %s has no linked analysis job id",
                    media.id,
                )

                media.status = "failed"

                media.error_message = (
                    "Analysis job missing."
                )

                reconciled += 1

                continue

            try:
                job = Job.fetch(
                    media.analysis_job_id,
                    connection=redis_conn,
                )

                job_status = job.get_status()

                logger.info(
                    "Media %s linked job %s status=%s",
                    media.id,
                    media.analysis_job_id,
                    job_status,
                )

                # healthy jobs
                if job_status in [
                    "queued",
                    "started",
                    "deferred",
                ]:
                    continue

                # unhealthy jobs
                if job.is_failed or job_status in [
                    "failed",
                    "stopped",
                    "canceled",
                ]:
                    media.status = "failed"

                    media.error_message = (
                        "Analysis job failed or timed out."
                    )

                    reconciled += 1

            except Exception:
                logger.warning(
                    "Missing or abandoned job for media %s",
                    media.id,
                )

                media.status = "failed"

                media.error_message = (
                    "Analysis job was abandoned or missing."
                )

                reconciled += 1

        db.commit()

        logger.info(
            "Reconciliation completed. "
            "Recovered %s stuck jobs.",
            reconciled,
        )

        return {
            "reconciled": reconciled,
        }

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")

        db.rollback()

        raise

    finally:
        db.close()


def cluster_images():
    """
    Background job to cluster all indexed images
    """

    from find_api.ml.clusterer import get_image_clusterer
    from find_api.models.cluster import Cluster

    db = SessionLocal()

    try:
        logger.info("Starting clustering job...")

        db.query(Media).filter(
            Media.cluster_id.isnot(None)
        ).update(
            {Media.cluster_id: None},
            synchronize_session=False,
        )

        db.query(Cluster).delete(
            synchronize_session=False
        )

        db.flush()

        media_rows = (
            db.query(Media.id, Media.vector)
            .filter(
                Media.status == "indexed",
                Media.vector.isnot(None),
            )
            .all()
        )

        if len(media_rows) < settings.MIN_CLUSTER_SIZE:

            db.commit()

            logger.warning(
                "Not enough images for clustering "
                "(found %s, need %s)",
                len(media_rows),
                settings.MIN_CLUSTER_SIZE,
            )

            return {
                "n_clusters": 0,
                "noise_points": len(media_rows),
                "total_points": len(media_rows),
                "message": (
                    "Not enough indexed images "
                    "for clustering"
                ),
            }

        embeddings = np.asarray(
            [row.vector for row in media_rows],
            dtype=np.float32,
        )

        media_ids = [row.id for row in media_rows]

        logger.info(f"Clustering {len(media_rows)} images...")

        clusterer = get_image_clusterer()

        labels, info = clusterer.cluster(embeddings)

        cluster_labels = sorted(
            {
                int(label)
                for label in labels
                if int(label) != -1
            }
        )

        if not cluster_labels:

            db.commit()

            logger.info(
                "Clustering completed with no stable clusters"
            )

            return {
                **info,
                "message": "No stable clusters found",
                "cluster_ids": [],
            }

        centroids = clusterer.compute_centroids(
            embeddings,
            labels,
        )

        cluster_records = {}

        for cluster_label in cluster_labels:

            member_ids = [
                media_ids[i]
                for i, label in enumerate(labels)
                if int(label) == cluster_label
            ]

            cluster = Cluster(
                cluster_type="general",
                member_ids=member_ids,
                member_count=len(member_ids),
                centroid_vector=centroids[
                    cluster_label
                ].tolist(),
            )

            db.add(cluster)

            db.flush()

            cluster_records[cluster_label] = cluster

        db.bulk_update_mappings(
            Media,
            [
                {
                    "id": media_id,
                    "cluster_id": None
                    if int(labels[index]) == -1
                    else cluster_records[
                        int(labels[index])
                    ].id,
                }
                for index, media_id in enumerate(media_ids)
            ],
        )

        db.commit()

        result = {
            **info,
            "message": "Clustering completed successfully",
            "cluster_ids": [
                cluster.id
                for cluster in cluster_records.values()
            ],
        }

        logger.info("Clustering complete: %s", result)

        return result

    except Exception as e:
        logger.error(f"Clustering failed: {e}")

        db.rollback()

        raise

    finally:
        clear_clustering_job_state()

        db.close()