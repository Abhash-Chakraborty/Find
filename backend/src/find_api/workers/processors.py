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
    "person", "people", "human", "man", "woman", "boy", "girl", "face",
}

# ---------------------------------------------------------------------------
# Remote ML dispatch helpers
# ---------------------------------------------------------------------------

def _remote_analyze_image(image: Image.Image) -> Dict[str, Any]:
    """Send the image to the remote Find ML server for the analyze stage."""
    from find_api.ml.remote_client import _feature_enabled, remote_analyze

    if not any(_feature_enabled(f) for f in ("caption", "detect", "ocr")):
        logger.info("Remote mode: no analyze features enabled; returning empty metadata.")
        return {
            "caption": "",
            "objects": [],
            "ocr_text": "",
            "text_blocks": [],
            "stage_status": {
                "object_detection": {"status": "skipped", "error": None},
                "captioning": {"status": "skipped", "error": None},
                "ocr": {"status": "skipped", "error": None},
                "embedding": {"status": "pending", "error": None},
            },
        }

    logger.info("Dispatching analyze to remote ML server")
    result = remote_analyze(image)
    result.setdefault(
        "stage_status",
        {
            "object_detection": {"status": "success", "error": None},
            "captioning": {"status": "success", "error": None},
            "ocr": {"status": "success", "error": None},
            "embedding": {"status": "pending", "error": None},
        },
    )
    return result

def _remote_embed_image(image: Image.Image, metadata: Dict[str, Any]) -> List[float]:
    """Send the image to the remote Find ML server for the embed stage."""
    from find_api.ml.remote_client import _feature_enabled, remote_embed

    if not _feature_enabled("embed"):
        logger.info("Remote mode: embed disabled; using mock embedder fallback.")
        return get_mock_embedder().embed_metadata(image, metadata)

    logger.info("Dispatching embed to remote ML server")
    return remote_embed(image, metadata)

# ---------------------------------------------------------------------------
# Existing helpers
# ---------------------------------------------------------------------------

def _safe_normalize_embedding(vector: np.ndarray, *, fallback: np.ndarray | None = None) -> np.ndarray:
    """Return a finite normalized embedding or a finite fallback vector."""
    clean_vector = np.nan_to_num(
        np.asarray(vector, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0,
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

# ---------------------------------------------------------------------------
# Public processor functions
# ---------------------------------------------------------------------------

def extract_image_metadata(
    image: Image.Image,
    on_stage: Callable[[str], None] | None = None,
) -> Dict[str, Any]:
    """Run all ML models to extract metadata from image."""
    # ---- Mock mode ----
    if settings.ML_MODE.lower() == "mock":
        if on_stage:
            on_stage("generating mock metadata")
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

    # ---- Remote mode ----
    if settings.ML_MODE.lower() == "remote":
        if on_stage:
            on_stage("sending to remote ML server")
        return _remote_analyze_image(image)

    # ---- Full / local mode ----
    metadata: Dict[str, Any] = {
        "stage_status": {
            "object_detection": {"status": "pending", "error": None},
            "captioning": {"status": "pending", "error": None},
            "ocr": {"status": "pending", "error": None},
            "embedding": {"status": "pending", "error": None},
        }
    }

    try:
        if on_stage: on_stage("detecting objects")
        from find_api.ml.object_detector import get_object_detector
        objects = get_object_detector().detect(image)
        metadata["objects"] = objects
        metadata["stage_status"]["object_detection"] = {"status": "success", "error": None}
    except Exception as e:
        metadata["objects"] = []
        _record_stage_error(metadata, "objects", e)
        metadata["stage_status"]["object_detection"] = {"status": "failed", "error": sanitize_error(e)}

    try:
        if on_stage: on_stage("generating caption")
        from find_api.ml.captioner import get_image_captioner
        caption = get_image_captioner().generate_caption(image)
        metadata["caption"] = caption
        metadata["stage_status"]["captioning"] = {"status": "success", "error": None}
        metadata["stage_status"]["captioning"] = {"status": "success", "error": None}
    except Exception as e:
        metadata["caption"] = ""
        _record_stage_error(metadata, "caption", e)
        metadata["stage_status"]["captioning"] = {"status": "failed", "error": sanitize_error(e)}

    try:
        if on_stage: on_stage("running OCR")
        from find_api.ml.ocr import get_ocr_extractor
        ocr = get_ocr_extractor()
        metadata["ocr_text"] = ocr.extract_text(image)
        metadata["text_blocks"] = ocr.extract_text_with_boxes(image)
        metadata["stage_status"]["ocr"] = {"status": "success", "error": None}
    except Exception as e:
        metadata["ocr_text"] = ""
        metadata["text_blocks"] = []
        _record_stage_error(metadata, "ocr", e)
        metadata["stage_status"]["ocr"] = {"status": "failed", "error": sanitize_error(e)}

    return metadata

def generate_hybrid_embedding(image: Image.Image, metadata: Dict[str, Any]) -> List[float]:
    """Generate hybrid embedding from image, caption, detected objects, and OCR text."""
    # ---- Mock mode ----
    if settings.ML_MODE.lower() == "mock":
        return get_mock_embedder().embed_metadata(image, metadata)

    # ---- Remote mode ----
    if settings.ML_MODE.lower() == "remote":
        return _remote_embed_image(image, metadata)

    # ---- Full / local mode ----
    try:
        from find_api.ml.clip_embedder import get_clip_embedder
        embedder = get_clip_embedder()

        image_embedding = _safe_normalize_embedding(embedder.embed_image(image))
        caption = (metadata.get("caption") or "").strip()

        raw_objects = metadata.get("objects") or []
        object_names_set = {str(obj.get("class", "")).strip() for obj in raw_objects if isinstance(obj, dict) and str(obj.get("class", "")).strip()}
        objects_text = "detected objects: " + ", ".join(sorted(object_names_set)) if object_names_set else ""
        ocr_text = (metadata.get("ocr_text") or "").strip()

        has_caption = bool(caption)
        has_objects = bool(objects_text)
        has_ocr = bool(ocr_text)

        text_inputs, text_signal_names = [], []
        if has_caption:
            text_inputs.append(caption)
            text_signal_names.append("caption")
        if has_objects:
            text_inputs.append(objects_text)
            text_signal_names.append("objects")
        if has_ocr:
            text_inputs.append(ocr_text)
            text_signal_names.append("ocr")

        signal_vectors = {"image": image_embedding}

        if text_inputs:
            if len(text_inputs) == 1:
                signal_vectors[text_signal_names[0]] = _safe_normalize_embedding(embedder.embed_text(text_inputs[0]))
            else:
                for name, vec in zip(text_signal_names, embedder.embed_text(text_inputs)):
                    signal_vectors[name] = _safe_normalize_embedding(vec)

        active_signals = list(signal_vectors.keys())

        if has_ocr:
            total_weight = sum(OCR_AWARE_SIGNAL_WEIGHTS.get(name, 0.0) for name in active_signals)
            if total_weight > 0:
                hybrid_vector = sum(signal_vectors[name] * (OCR_AWARE_SIGNAL_WEIGHTS.get(name, 0.0) / total_weight) for name in active_signals)
            else:
                hybrid_vector = image_embedding
        else:
            hybrid_vector = sum(signal_vectors.values()) / len(signal_vectors)

        return _safe_normalize_embedding(hybrid_vector, fallback=image_embedding).tolist()
    except Exception:
        logger.exception("CLIP embedding failed")
        raise

def has_person_object(metadata: Dict[str, Any]) -> bool:
    """Return true when object detection found a person-like object."""
    for obj in (metadata.get("objects") or []):
        if not isinstance(obj, dict): continue
        label = str(obj.get("class") or obj.get("name") or obj.get("label") or "").strip().lower()
        if label in PERSON_OBJECT_LABELS: return True
    return False

def detect_and_store_faces(image: Image.Image, media_id: int, db) -> int:
    """Detect faces in image and store them in the database."""
    from find_api.models.face import Face

    if settings.ML_MODE.lower() in ("mock", "remote"):
        return 0

    try:
        from find_api.ml.face_detector import get_face_detector
        faces = get_face_detector().detect_faces(image)
        db.query(Face).filter(Face.media_id == media_id).delete(synchronize_session=False)

        if not faces:
            db.commit()
            return 0

        stored_count = 0
        for face_data in faces:
            bbox = face_data.get("bbox")
            embedding = face_data.get("embedding")
            confidence = face_data.get("confidence")
            if None in (bbox, embedding, confidence): continue

            db.add(Face(media_id=media_id, bounding_box=bbox, embedding=embedding, confidence=confidence))
            stored_count += 1

        db.commit()
        return stored_count
    except Exception:
        db.rollback()
        return 0
