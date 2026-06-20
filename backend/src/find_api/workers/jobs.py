"""
Background worker jobs for image processing
"""

from PIL import Image
import io
import logging
from datetime import datetime
import numpy as np
from rq import get_current_job

from find_api.core.database import SessionLocal
from find_api.core.queue import (
    clear_clustering_job_state,
    clear_feedback_ranking_job_state,
    enqueue_clustering_job,
)
from find_api.core.storage import get_file, upload_thumbnail
from find_api.core.model_manager import get_model_manager
from find_api.core.config import settings
from find_api.models.media import Media
from find_api.services.query_cache import invalidate_query_cache
from find_api.utils.exif import extract_exif_data
from find_api.utils.errors import sanitize_error

from sqlalchemy import func
from find_api.models.feedback import GeneralFeedback

logger = logging.getLogger(__name__)

# Start ML model cleanup for the worker process
try:
    get_model_manager().start_autocleanup(
        ttl_seconds=settings.ML_MODEL_IDLE_TTL_SECONDS,
        process_name="worker",
    )
except Exception as e:
    logger.error(f"Failed to start model cleanup thread in worker: {e}")

FACE_CLUSTER_NAME_MATCH_THRESHOLD = 0.72
ANALYSIS_MODEL_NAMES = ("yolo", "florence-2", "paddleocr", "siglip", "insightface")


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine similarity for two vectors, guarding empty norms."""
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def set_stage(job, stage: str):
    """Persist the current upload-processing stage in RQ metadata."""
    if job:
        job.meta["stage"] = stage
        job.save_meta()


def set_error(job, error: str):
    """Persist a safe user-facing processing error in RQ metadata."""
    if job:
        job.meta["error"] = error
        job.save_meta()


def generate_thumbnail_for_media(media_id: int):
    """Generate a missing thumbnail without rerunning the full ML analysis."""
    db = SessionLocal()
    try:
        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            logger.warning("Thumbnail backfill skipped: media %s not found", media_id)
            return {"status": "not_found", "media_id": media_id}

        if media.thumbnail_key:
            return {"status": "skipped", "media_id": media_id, "reason": "exists"}

        image_data = get_file(media.minio_key)
        thumbnail_metadata = upload_thumbnail(image_data, media.file_hash)
        if not thumbnail_metadata:
            return {
                "status": "failed",
                "media_id": media_id,
                "reason": "thumbnail_generation_failed",
            }

        for key, value in thumbnail_metadata.items():
            setattr(media, key, value)
        db.commit()
        invalidate_query_cache()
        return {"status": "success", "media_id": media_id}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Thumbnail backfill failed for media %s: %s", media_id, exc)
        return {"status": "failed", "media_id": media_id, "reason": sanitize_error(exc)}
    finally:
        db.close()


def analyze_image(media_id: int, clear_model_failures: bool = False):
    """
    Main worker job to analyze an uploaded image
    """

    from find_api.workers.processors import (
        extract_image_metadata,
        generate_hybrid_embedding,
    )

    job = get_current_job()

    db = SessionLocal()
    media = None
    metadata = None

    try:
        if clear_model_failures:
            get_model_manager().clear_model_failures(ANALYSIS_MODEL_NAMES)

        set_stage(job, "loading image")

        media = db.query(Media).filter(Media.id == media_id).first()
        if not media:
            logger.error(f"Media {media_id} not found")
            return

        media.status = "processing"
        db.commit()

        image_data = get_file(media.minio_key)
        image = Image.open(io.BytesIO(image_data))

        if image.mode != "RGB":
            image = image.convert("RGB")

        media.width, media.height = image.size

        if not media.thumbnail_key:
            set_stage(job, "generating thumbnail")
            thumbnail_metadata = upload_thumbnail(image_data, media.file_hash)
            if thumbnail_metadata:
                for key, value in thumbnail_metadata.items():
                    setattr(media, key, value)

        set_stage(job, "extracting EXIF")

        try:
            exif_data = extract_exif_data(image)
            media.exif_json = exif_data
        except Exception as e:
            logger.warning(f"Failed to extract EXIF: {e}")
            media.exif_json = {}

        metadata = extract_image_metadata(
            image,
            on_stage=lambda stage: set_stage(job, stage),
        )

        set_stage(job, "generating embedding")

        try:
            media.vector = generate_hybrid_embedding(image, metadata)
            if "stage_status" in metadata:
                metadata["stage_status"]["embedding"] = {
                    "status": "success",
                    "error": None,
                }
        except Exception as e:
            if "stage_status" in metadata:
                metadata["stage_status"]["embedding"] = {
                    "status": "failed",
                    "error": sanitize_error(e),
                }
            raise

        set_stage(job, "indexing complete")

        media.metadata_json = metadata
        media.status = "indexed"
        media.processed_at = datetime.utcnow()

        db.commit()
        invalidate_query_cache()

        # near-duplicate detection
        try:
            from find_api.services.duplicate_service import (
                find_near_duplicate,
                flag_as_duplicate,
            )

            if media.vector is not None:
                dup_id = find_near_duplicate(
                    db=db, media_id=media.id, embedding=media.vector
                )
                if dup_id is not None:
                    flag_as_duplicate(db=db, media_id=media.id, duplicate_of=dup_id)
        except Exception as e:
            db.rollback()
            logger.warning("Near-duplicate check failed for media %s: %s", media_id, e)

        from find_api.workers.processors import (
            detect_and_store_faces,
            has_person_object,
        )

        if has_person_object(metadata):
            set_stage(job, "detecting faces")
            face_count = detect_and_store_faces(image, media_id, db)
            logger.info("Face detection complete: %s faces found", face_count)
        else:
            logger.info(
                "Skipping face detection for media %s: no person object detected",
                media_id,
            )

        set_stage(job, "clustering queued")

        try:
            enqueue_clustering_job(reason=f"media:{media_id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Indexed media %s but failed to queue clustering: %s",
                media_id,
                exc,
            )

        logger.info(f"Successfully processed media {media_id}")

        # Post-job memory cleanup
        try:
            get_model_manager().unload_idle_models(settings.ML_MODEL_IDLE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Cleanup failed after processing media {media_id}: {e}")

        return {"media_id": media_id, "status": "success", "metadata": metadata}

    except Exception as e:
        logger.error(f"Failed to process media {media_id}: {e}")
        db.rollback()

        safe_error = sanitize_error(e)
        set_stage(job, "failed")
        set_error(job, safe_error)

        if media:
            media.status = "failed"
            media.error_message = safe_error
            if metadata:
                media.metadata_json = metadata
            db.commit()

        raise

    finally:
        db.close()


def cluster_images():
    """
    Background job to cluster all indexed images
    """

    from find_api.ml.clusterer import get_image_clusterer
    from find_api.models.cluster import Cluster
    from find_api.core.config import settings

    db = SessionLocal()

    try:
        logger.info("Starting clustering job...")

        # Step 1: Read data — no DB mutations yet.
        media_rows = (
            db.query(Media.id, Media.vector)
            .filter(Media.status == "indexed", Media.vector.isnot(None))
            .all()
        )
        # Step 2: Validate minimum size BEFORE touching anything.
        if len(media_rows) < settings.MIN_CLUSTER_SIZE:
            logger.warning(
                "Not enough images for clustering (found %s, need %s)",
                len(media_rows),
                settings.MIN_CLUSTER_SIZE,
            )
            return {
                "n_clusters": 0,
                "noise_points": len(media_rows),
                "total_points": len(media_rows),
                "message": "Not enough indexed images for clustering",
            }

        embeddings = np.asarray([row.vector for row in media_rows], dtype=np.float32)
        media_ids = [row.id for row in media_rows]

        logger.info(f"Clustering {len(media_rows)} images...")

        # Step 3: Run clustering — pure computation, no DB.

        clusterer = get_image_clusterer()
        labels, info = clusterer.cluster(embeddings)

        cluster_labels = sorted({int(label) for label in labels if int(label) != -1})
        # Step 4: Validate result BEFORE touching anything.
        if not cluster_labels:
            logger.info("Clustering completed with no stable clusters")
            return {
                **info,
                "message": "No stable clusters found",
                "cluster_ids": [],
            }

        centroids = clusterer.compute_centroids(embeddings, labels)
        # Step 5: Now safe to mutate — valid new state exists.
        db.query(Media).filter(Media.cluster_id.isnot(None)).update(
            {Media.cluster_id: None}, synchronize_session=False
        )
        db.query(Cluster).delete(synchronize_session=False)
        db.flush()

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
                centroid_vector=centroids[cluster_label].tolist(),
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
                    else cluster_records[int(labels[index])].id,
                }
                for index, media_id in enumerate(media_ids)
            ],
        )

        db.commit()  # ← single commit: delete old + insert new, atomically
        invalidate_query_cache()

        result = {
            **info,
            "message": "Clustering completed successfully",
            "cluster_ids": [cluster.id for cluster in cluster_records.values()],
        }
        logger.info("Clustering complete: %s", result)

        # Post-job memory cleanup
        try:
            get_model_manager().unload_idle_models(settings.ML_MODEL_IDLE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Cleanup failed after clustering images: {e}")

        return result

    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        db.rollback()
        raise

    finally:
        clear_clustering_job_state()
        db.close()


def process_feedback_ranking():
    """
    Background job to compute tiny ranking boosts
    from accumulated local feedback.
    """

    db = SessionLocal()

    try:
        logger.info("Starting feedback ranking update...")

        media_items = db.query(Media).filter(Media.status == "indexed").all()

        feedback_scores = (
            db.query(
                GeneralFeedback.media_id,
                func.avg(GeneralFeedback.rating).label("avg_rating"),
            )
            .filter(
                GeneralFeedback.feedback_type == "search_rating",
            )
            .group_by(GeneralFeedback.media_id)
            .all()
        )

        score_map = {media_id: avg_rating for media_id, avg_rating in feedback_scores}

        for media in media_items:
            avg_rating = score_map.get(media.id)

            boost = 0.0

            # tiny boost for liked images
            if media.liked:
                boost += 0.02

            # tiny adjustment from ratings
            if avg_rating is not None:
                boost += (float(avg_rating) - 3.0) * 0.01

            # keep semantic search dominant
            boost = max(min(boost, 0.05), -0.05)

            media.ranking_boost = boost

        db.commit()

        logger.info("Feedback ranking update complete")

        return {"status": "success"}

    except Exception as e:
        logger.error("Feedback ranking failed: %s", e)
        db.rollback()
        raise

    finally:
        clear_feedback_ranking_job_state()
        db.close()


def cluster_faces():
    """
    Background job to cluster all detected faces into person groups.

    How it works:
    1. Load all face embeddings from the database
    2. Check we have enough faces BEFORE deleting anything
    3. Run HDBSCAN to group similar faces together
    4. Create a Person row for each group
    5. Link each face to its Person group
    """
    from find_api.ml.clusterer import get_image_clusterer
    from find_api.models.face import Face
    from find_api.models.person import Person

    db = SessionLocal()

    try:
        logger.info("Starting face clustering job...")

        # Step 1: Load all faces that have embeddings.
        # Check BEFORE changing assignments so names are not lost on no-op runs.
        face_rows = (
            db.query(Face.id, Face.embedding).filter(Face.embedding.isnot(None)).all()
        )

        # Need at least 2 faces to cluster
        if len(face_rows) < 2:
            db.commit()
            logger.warning(
                "Not enough faces for clustering (found %s, need 2)",
                len(face_rows),
            )
            return {
                "n_clusters": 0,
                "total_faces": len(face_rows),
                "message": "Not enough faces for clustering",
            }

        named_person_centroids = {}
        named_people = db.query(Person).filter(Person.name.isnot(None)).all()
        for person in named_people:
            person_faces = (
                db.query(Face.embedding)
                .filter(Face.person_id == person.id, Face.embedding.isnot(None))
                .all()
            )
            embeddings_for_person = [
                row.embedding for row in person_faces if row.embedding is not None
            ]
            if embeddings_for_person:
                named_person_centroids[person.id] = {
                    "name": person.name,
                    "centroid": np.asarray(
                        embeddings_for_person, dtype=np.float32
                    ).mean(axis=0),
                }

        # Step 2: Prepare embeddings as numpy array
        embeddings = np.asarray([row.embedding for row in face_rows], dtype=np.float32)
        face_ids = [row.id for row in face_rows]

        logger.info("Clustering %s faces...", len(face_rows))

        # Step 4: Run HDBSCAN clustering
        clusterer = get_image_clusterer()
        labels, info = clusterer.cluster(embeddings)

        # Step 5: Create Person rows for each cluster
        # label -1 means noise - skip those
        unique_labels = sorted({int(label) for label in labels if int(label) != -1})

        if not unique_labels:
            db.commit()
            logger.info("Face clustering found no stable person groups")
            return {
                **info,
                "message": "No stable person groups found",
            }

        # Step 5: Only reset assignments once we know clustering will proceed.
        # Keep named people available so stable re-clusters can preserve labels.
        db.query(Face).update({Face.person_id: None}, synchronize_session=False)
        db.query(Person).filter(Person.name.is_(None)).delete(synchronize_session=False)
        db.flush()

        cluster_centroids = {}
        for label in unique_labels:
            cluster_embeddings = embeddings[
                np.asarray([int(item) == label for item in labels])
            ]
            cluster_centroids[label] = cluster_embeddings.mean(axis=0)

        # Create one Person per cluster label, reusing named people when the
        # new cluster is close enough to its previous centroid.
        person_records = {}
        reused_person_ids = set()
        for label in unique_labels:
            best_person_id = None
            best_score = FACE_CLUSTER_NAME_MATCH_THRESHOLD
            for person_id, person_info in named_person_centroids.items():
                if person_id in reused_person_ids:
                    continue
                score = cosine_similarity(
                    cluster_centroids[label], person_info["centroid"]
                )
                if score > best_score:
                    best_score = score
                    best_person_id = person_id

            if best_person_id is not None:
                person = db.query(Person).filter(Person.id == best_person_id).first()
                reused_person_ids.add(best_person_id)
            else:
                person = Person()
                db.add(person)
                db.flush()

            if person is None:
                person = Person()
                db.add(person)
                db.flush()
            person_records[label] = person

        # Step 6: Link each face to its Person
        for face_id, label in zip(face_ids, labels):
            if int(label) == -1:
                continue
            person = person_records[int(label)]
            db.query(Face).filter(Face.id == face_id).update(
                {Face.person_id: person.id},
                synchronize_session=False,
            )

        assigned_person_ids = (
            db.query(Face.person_id).filter(Face.person_id.isnot(None)).distinct()
        )
        db.query(Person).filter(Person.id.notin_(assigned_person_ids)).delete(
            synchronize_session=False
        )

        db.commit()

        result = {
            **info,
            "n_persons": len(unique_labels),
            "message": "Face clustering completed successfully",
        }
        logger.info("Face clustering complete: %s", result)

        # Post-job memory cleanup
        try:
            get_model_manager().unload_idle_models(settings.ML_MODEL_IDLE_TTL_SECONDS)
        except Exception as e:
            logger.warning(f"Cleanup failed after clustering faces: {e}")

        return result

    except Exception as e:
        logger.error("Face clustering failed: %s", e)
        db.rollback()
        raise

    finally:
        db.close()
