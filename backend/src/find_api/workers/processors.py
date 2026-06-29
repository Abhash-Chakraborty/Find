"""
Image processing utilities for worker jobs
"""

import logging
from collections.abc import Callable
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from find_api.core.config import settings
from find_api.core.model_manager import ModelUnavailableError
from find_api.ml.mock_embedder import get_mock_embedder
from find_api.utils.errors import sanitize_error

logger = logging.getLogger(__name__)

# OCR-present assets use weighted fusion to improve text-centric retrieval.
OCR_AWARE_SIGNAL_WEIGHTS = {
    "image": 0.40,
    "caption": 0.25,
    "objects": 0.15,
    "ocr": 0.20,
}

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


def _safe_normalize_embedding(
    vector: np.ndarray,
    *,
    fallback: np.ndarray | None = None,
) -> np.ndarray:
    """Return a finite normalized embedding or a finite fallback vector."""
    clean_vector = np.nan_to_num(
        np.asarray(vector, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    norm = np.linalg.norm(clean_vector)

    if np.isfinite(norm) and norm > 0:
        return (clean_vector / norm).astype(np.float32)

    if fallback is not None:
        return _safe_normalize_embedding(fallback)

    return np.zeros_like(clean_vector, dtype=np.float32)


def _record_stage_error(metadata: Dict[str, Any], stage: str, error: Exception) -> None:
    """Store a safe, user-facing stage failure without stack traces."""
    if isinstance(error, ModelUnavailableError):
        message = str(error)
    else:
        message = f"{stage} failed during processing."

    metadata.setdefault("stage_errors", {})[stage] = message


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
        _record_stage_error(metadata, "objects", e)
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
        _record_stage_error(metadata, "caption", e)
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
        ocr_text, text_blocks = ocr.extract_text_and_boxes(image)
        metadata["ocr_text"] = ocr_text
        metadata["text_blocks"] = text_blocks
        metadata["stage_status"]["ocr"] = {"status": "success", "error": None}
        logger.info(f"Extracted {len(ocr_text)} characters")
    except Exception as e:
        logger.exception("OCR failed")
        metadata["ocr_text"] = ""
        metadata["text_blocks"] = []
        _record_stage_error(metadata, "ocr", e)
        metadata["stage_status"]["ocr"] = {
            "status": "failed",
            "error": sanitize_error(e),
        }

    return metadata


def generate_hybrid_embedding(
    image: Image.Image, metadata: Dict[str, Any]
) -> List[float]:
    """
    Generate hybrid embedding from image, caption, detected objects, and OCR text.

        Weighted average depends on which text signals are present:
      - image + caption + objects  →  equal thirds  (1/3 each)
      - image + caption only       →  halves         (1/2 each)
      - image + objects only       →  halves         (1/2 each)
      - image only                 →  image vector directly

        When OCR text is present, we apply OCR-aware weights and normalise them
        across active signals to prioritize text relevance for document-like images.

    Empty strings are never passed to embed_text() because CLIP encodes
    them as a deterministic non-zero vector that would introduce a
    systematic bias across all images lacking that signal.
    """
    if settings.ML_MODE.lower() == "mock":
        logger.info("Using mock embedding generator")
        return get_mock_embedder().embed_metadata(image, metadata)

    try:
        logger.info("Generating CLIP embedding...")
        from find_api.ml.clip_embedder import get_clip_embedder

        embedder = get_clip_embedder()

        # --- 1. Image vector (always computed) ---
        image_embedding = _safe_normalize_embedding(embedder.embed_image(image))

        # --- 2. Build text signals — only non-empty strings qualify ---
        caption = (metadata.get("caption") or "").strip()

        raw_objects = metadata.get("objects") or []
        object_names_set: set[str] = set()
        for obj in raw_objects:
            if not isinstance(obj, dict):
                continue

            label = str(obj.get("class", "")).strip()
            if label:
                object_names_set.add(label)

        object_names = sorted(object_names_set)
        objects_text = (
            "detected objects: " + ", ".join(object_names) if object_names else ""
        )

        ocr_text = (metadata.get("ocr_text") or "").strip()

        has_caption = bool(caption)
        has_objects = bool(objects_text)
        has_ocr = bool(ocr_text)

        # --- 3. Embed only what exists, in a single model pass where possible ---
        text_inputs: list[str] = []
        text_signal_names: list[str] = []
        if has_caption:
            text_inputs.append(caption)
            text_signal_names.append("caption")
        if has_objects:
            text_inputs.append(objects_text)
            text_signal_names.append("objects")
        if has_ocr:
            text_inputs.append(ocr_text)
            text_signal_names.append("ocr")

        signal_vectors: dict[str, np.ndarray] = {"image": image_embedding}

        if text_inputs:
            if len(text_inputs) == 1:
                signal_vectors[text_signal_names[0]] = _safe_normalize_embedding(
                    embedder.embed_text(text_inputs[0])
                )
            else:
                text_embeddings = embedder.embed_text(text_inputs)
                for name, vec in zip(text_signal_names, text_embeddings):
                    signal_vectors[name] = _safe_normalize_embedding(vec)

        active_signals = list(signal_vectors.keys())

        if has_ocr:
            total_weight = sum(
                OCR_AWARE_SIGNAL_WEIGHTS.get(name, 0.0) for name in active_signals
            )
            if total_weight > 0:
                hybrid_vector = sum(
                    signal_vectors[name]
                    * (OCR_AWARE_SIGNAL_WEIGHTS.get(name, 0.0) / total_weight)
                    for name in active_signals
                )
            else:
                hybrid_vector = image_embedding
        else:
            # Preserve prior behavior for non-OCR assets.
            n = len(signal_vectors)
            hybrid_vector = sum(signal_vectors.values()) / n

        hybrid_vector = _safe_normalize_embedding(
            hybrid_vector,
            fallback=image_embedding,
        )

        logger.info(
            "Hybrid embedding generated (signals=%d: %s, ocr_weighting=%s)",
            len(active_signals),
            active_signals,
            has_ocr,
        )
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
