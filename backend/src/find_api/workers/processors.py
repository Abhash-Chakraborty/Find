"""
Image processing utilities for worker jobs
"""

import logging
from collections.abc import Callable
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from find_api.core.config import settings
from find_api.ml.mock_embedder import get_mock_embedder
from find_api.utils.errors import sanitize_error

logger = logging.getLogger(__name__)

PERSON_OBJECT_LABELS = {
    "person",
    "people",
    "human",
    "man",
    "woman",
    "boy",
    "girl",
    "face",
}


def extract_image_metadata(
    image: Image.Image,
    on_stage: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    """
    Run all ML models to extract metadata from image
    """
    if settings.ML_MODE.lower() == "mock":
        if on_stage:
            on_stage("generating mock metadata")
        logger.info("Using mock image metadata extractor")
        return {
            "caption": f"Mock caption for {image.width}x{image.height} image",
            "objects": [],
            "ocr_text": "",
            "text_blocks": [],
            "mock": True,
            "stage_status": {
                "object_detection": {"status": "success", "error": None},
                "captioning": {"status": "success", "error": None},
                "ocr": {"status": "success", "error": None},
                "embedding": {"status": "pending", "error": None},
            },
        }

    metadata = {
        "stage_status": {
            "object_detection": {"status": "pending", "error": None},
            "captioning": {"status": "pending", "error": None},
            "ocr": {"status": "pending", "error": None},
            "embedding": {"status": "pending", "error": None},
        }
    }

    # 1. Object Detection
    try:
        if on_stage:
            on_stage("detecting objects")
        logger.info("Running object detection...")
        from find_api.ml.object_detector import get_object_detector

        detector = get_object_detector()
        objects = detector.detect(image)
        metadata["objects"] = objects
        metadata["stage_status"]["object_detection"] = {
            "status": "success",
            "error": None,
        }
        logger.info(f"Detected {len(objects)} objects")
    except Exception as e:
        logger.exception("Object detection failed")
        metadata["objects"] = []
        metadata["stage_status"]["object_detection"] = {
            "status": "failed",
            "error": sanitize_error(e),
        }

    # 2. Image Captioning
    try:
        if on_stage:
            on_stage("generating caption")
        logger.info("Generating caption...")
        from find_api.ml.captioner import get_image_captioner

        captioner = get_image_captioner()
        caption = captioner.generate_caption(image)
        metadata["caption"] = caption
        metadata["stage_status"]["captioning"] = {"status": "success", "error": None}
        logger.info(f"Caption: {caption}")
    except Exception as e:
        logger.exception("Captioning failed")
        metadata["caption"] = ""
        metadata["stage_status"]["captioning"] = {
            "status": "failed",
            "error": sanitize_error(e),
        }

    # 3. OCR Text Extraction
    try:
        if on_stage:
            on_stage("running OCR")
        logger.info("Extracting text...")
        from find_api.ml.ocr import get_ocr_extractor

        ocr = get_ocr_extractor()
        ocr_text = ocr.extract_text(image)
        text_blocks = ocr.extract_text_with_boxes(image)
        metadata["ocr_text"] = ocr_text
        metadata["text_blocks"] = text_blocks
        metadata["stage_status"]["ocr"] = {"status": "success", "error": None}
        logger.info(f"Extracted {len(ocr_text)} characters")
    except Exception as e:
        logger.exception("OCR failed")
        metadata["ocr_text"] = ""
        metadata["text_blocks"] = []
        metadata["stage_status"]["ocr"] = {
            "status": "failed",
            "error": sanitize_error(e),
        }

    return metadata


def generate_hybrid_embedding(
    image: Image.Image, metadata: Dict[str, Any]
) -> List[float]:
    """
    Generate hybrid embedding from image, caption, and objects
    """
    if settings.ML_MODE.lower() == "mock":
        logger.info("Using mock embedding generator")
        return get_mock_embedder().embed_metadata(image, metadata)

    try:
        logger.info("Generating CLIP embedding...")
        from find_api.ml.clip_embedder import get_clip_embedder

        embedder = get_clip_embedder()

        # Generate Image Embedding
        image_embedding = embedder.embed_image(image)

        # Generate caption/object text embeddings in one model pass.
        objects = metadata.get("objects", [])
        object_names = [obj["class"] for obj in objects]
        if object_names:
            objects_text = "detected objects: " + ", ".join(
                sorted(list(set(object_names)))
            )
        else:
            objects_text = ""
        caption_embedding, objects_embedding = embedder.embed_text(
            [metadata.get("caption", ""), objects_text]
        )

        # Create Hybrid Vector (Average)
        hybrid_vector = (image_embedding + caption_embedding + objects_embedding) / 3.0

        # Normalize
        hybrid_vector = hybrid_vector / np.linalg.norm(hybrid_vector)

        logger.info("Hybrid embedding generated")
        return hybrid_vector.tolist()

    except Exception:
        logger.exception("CLIP embedding failed")
        raise


def has_person_object(metadata: Dict[str, Any]) -> bool:
    """Return true when object detection found a person-like object."""
    objects = metadata.get("objects") or []

    for obj in objects:
        if not isinstance(obj, dict):
            continue

        label = (
            str(obj.get("class") or obj.get("name") or obj.get("label") or "")
            .strip()
            .lower()
        )
        if not label:
            continue

        if label in PERSON_OBJECT_LABELS:
            return True

    return False


def detect_and_store_faces(image: Image.Image, media_id: int, db) -> int:
    """
    Detect faces in image and store them in the database.
    Returns the number of faces detected.

    In mock mode: skips detection entirely (no model needed).
    In real mode: uses InsightFace antelopev2 to detect faces.
    """
    # Import here to avoid circular imports
    from find_api.models.face import Face

    # Mock mode - skip face detection entirely
    # This keeps light/mock mode working without downloading face models
    if settings.ML_MODE.lower() == "mock":
        logger.info("Mock mode: skipping face detection for media %s", media_id)
        return 0

    # Real mode - run actual face detection
    try:
        logger.info("Running face detection for media %s...", media_id)
        from find_api.ml.face_detector import get_face_detector

        detector = get_face_detector()
        faces = detector.detect_faces(image)

        db.query(Face).filter(Face.media_id == media_id).delete(
            synchronize_session=False
        )

        if not faces:
            db.commit()
            logger.info("No faces detected in media %s", media_id)
            return 0

        # Save each detected face to the database
        stored_count = 0
        for face_data in faces:
            bbox = face_data.get("bbox")
            embedding = face_data.get("embedding")
            confidence = face_data.get("confidence")
            if bbox is None or embedding is None or confidence is None:
                logger.warning("Skipping malformed face payload for media %s", media_id)
                continue

            db.add(
                Face(
                    media_id=media_id,
                    bounding_box=bbox,
                    embedding=embedding,
                    confidence=confidence,
                    # person_id is None for now - set after clustering
                )
            )
            stored_count += 1

        if stored_count == 0:
            db.commit()
            logger.info("No valid faces to store for media %s", media_id)
            return 0

        db.commit()
        logger.info("Stored %s faces for media %s", stored_count, media_id)
        return stored_count

    except Exception:
        logger.exception("Face detection failed for media %s", media_id)
        db.rollback()
        # Don't raise - face detection failure should not fail the whole job
        return 0
