"""
Image processing utilities for worker jobs
"""

import logging
from collections.abc import Callable
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from find_api.core.model_manager import ModelUnavailableError
from find_api.core.runtime_profile import current_ml_mode
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

# ---------------------------------------------------------------------------
# Remote ML dispatch helpers
# ---------------------------------------------------------------------------


# REMOTE_ML_FEATURES stage name -> the stage_status key it controls.
_REMOTE_ANALYZE_STAGES = {
    "detect": "object_detection",
    "caption": "captioning",
    "ocr": "ocr",
}


class RemoteFeatureDisabled(Exception):
    """Raised when a remote stage is switched off in REMOTE_ML_FEATURES."""


def _remote_analyze_image(image: Image.Image) -> Dict[str, Any]:
    """Send the image to the remote Find ML server for the analyze stage.

    The enabled feature list is carried through to the server, which runs only
    those stages. Checking the list here and then letting the server run
    everything would make REMOTE_ML_FEATURES cosmetic: switching `ocr` off
    would still have the remote host OCR the image.
    """
    from find_api.ml.remote_client import _feature_enabled, remote_analyze

    requested = [name for name in _REMOTE_ANALYZE_STAGES if _feature_enabled(name)]
    disabled_status = {
        stage: {"status": "skipped", "error": None}
        for name, stage in _REMOTE_ANALYZE_STAGES.items()
        if name not in requested
    }

    if not requested:
        logger.info("Remote mode: no analyze features enabled; nothing is transmitted.")
        return {
            "caption": "",
            "objects": [],
            "ocr_text": "",
            "text_blocks": [],
            "stage_status": {
                **disabled_status,
                "embedding": {"status": "pending", "error": None},
            },
        }

    logger.info("Dispatching analyze to remote ML server (features=%s)", requested)
    result = remote_analyze(image, features=requested)

    # A disabled stage must never be reported as "success" -- it did not run.
    stage_status = result.get("stage_status") or {
        stage: {"status": "success", "error": None}
        for stage in _REMOTE_ANALYZE_STAGES.values()
    }
    stage_status.update(disabled_status)
    stage_status.setdefault("embedding", {"status": "pending", "error": None})
    result["stage_status"] = stage_status
    return result


def _remote_embed_image(image: Image.Image, metadata: Dict[str, Any]) -> List[float]:
    """Send the image to the remote Find ML server for the embed stage."""
    from find_api.ml.remote_client import _feature_enabled, remote_embed

    if not _feature_enabled("embed"):
        # Deliberately not a mock vector. Persisting one would put a
        # semantically meaningless embedding into the same column real vectors
        # live in, so the image would be searchable and always wrong. The
        # caller skips vector persistence instead.
        raise RemoteFeatureDisabled(
            "Remote embedding is disabled in REMOTE_ML_FEATURES."
        )

    logger.info("Dispatching embed to remote ML server")
    return remote_embed(image, metadata)


# ---------------------------------------------------------------------------
# Existing helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public processor functions
# ---------------------------------------------------------------------------


def extract_image_metadata(
    image: Image.Image,
    on_stage: Callable[[str], None] | None = None,
    stages: set[str] | None = None,
) -> Dict[str, Any]:
    """
    Run all ML models to extract metadata from image

    ``stages`` optionally restricts which of "detect"/"caption"/"ocr" run;
    omitted stages report "skipped". This is what lets a Find instance acting
    as a remote ML server honour the client's REMOTE_ML_FEATURES instead of
    running everything regardless.
    """
    mode = current_ml_mode()
    wanted = set(_REMOTE_ANALYZE_STAGES) if stages is None else set(stages)

    # ---- Mock mode ----
    if mode == "mock":
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

    # ---- Remote mode ----
    if mode == "remote":
        if on_stage:
            on_stage("sending to remote ML server")
        return _remote_analyze_image(image)

    # Protect local execution
    if mode != "full":
        raise RuntimeError(f"AI metadata extraction is unavailable in mode '{mode}'.")

    # ---- Full / local mode ----
    metadata: Dict[str, Any] = {
        "stage_status": {
            "object_detection": {"status": "pending", "error": None},
            "captioning": {"status": "pending", "error": None},
            "ocr": {"status": "pending", "error": None},
            "embedding": {"status": "pending", "error": None},
        }
    }

    # A stage the caller did not ask for must not run at all, and must be
    # reported as skipped rather than left "pending".
    for name, stage in _REMOTE_ANALYZE_STAGES.items():
        if name not in wanted:
            metadata["stage_status"][stage] = {"status": "skipped", "error": None}

    # 1. Object Detection
    if "detect" in wanted:
        try:
            if on_stage:
                on_stage("detecting objects")
            logger.info("Running object detection...")
            from find_api.ml.object_detector import get_object_detector

            objects = get_object_detector().detect(image)
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
    else:
        metadata["objects"] = []

    # 2. Image Captioning
    if "caption" in wanted:
        try:
            if on_stage:
                on_stage("generating caption")
            logger.info("Generating caption...")
            from find_api.ml.captioner import get_image_captioner

            caption = get_image_captioner().generate_caption(image)
            metadata["caption"] = caption
            metadata["stage_status"]["captioning"] = {
                "status": "success",
                "error": None,
            }
        except Exception as e:
            logger.exception("Captioning failed")
            metadata["caption"] = ""
            _record_stage_error(metadata, "caption", e)
            metadata["stage_status"]["captioning"] = {
                "status": "failed",
                "error": sanitize_error(e),
            }
    else:
        metadata["caption"] = ""

    # 3. OCR Text Extraction
    if "ocr" in wanted:
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
    else:
        metadata["ocr_text"] = ""
        metadata["text_blocks"] = []

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
    mode = current_ml_mode()

    # ---- Mock mode ----
    if mode == "mock":
        logger.info("Using mock embedding generator")
        return get_mock_embedder().embed_metadata(image, metadata)

    # ---- Remote mode ----
    if mode == "remote":
        return _remote_embed_image(image, metadata)

    # Protect local execution
    if mode != "full":
        raise RuntimeError(f"AI embedding generation is unavailable in mode '{mode}'.")

    # ---- Full / local mode ----
    try:
        logger.info("Generating CLIP embedding...")
        from find_api.ml.clip_embedder import get_clip_embedder

        embedder = get_clip_embedder()

        # --- 1. Image vector (always computed) ---
        image_embedding = _safe_normalize_embedding(embedder.embed_image(image))

        # --- 2. Build text signals — only non-empty strings qualify ---
        caption = (metadata.get("caption") or "").strip()

        raw_objects = metadata.get("objects") or []
        object_names_set = {
            str(obj.get("class", "")).strip()
            for obj in raw_objects
            if isinstance(obj, dict) and str(obj.get("class", "")).strip()
        }
        objects_text = (
            "detected objects: " + ", ".join(sorted(object_names_set))
            if object_names_set
            else ""
        )
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
    for obj in metadata.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        label = (
            str(obj.get("class") or obj.get("name") or obj.get("label") or "")
            .strip()
            .lower()
        )
        if label in PERSON_OBJECT_LABELS:
            return True
    return False


def detect_and_store_faces(image: Image.Image, media_id: int, db) -> int:
    """
    Detect faces in image and store them in the database.
    Returns the number of faces detected.

    In mock mode: skips detection entirely (no model needed).
    In remote mode: skips detection -- faces are deliberately not offloaded,
    since there is no face endpoint and biometric data is the last thing that
    should leave the machine by default.
    In real mode: uses InsightFace antelopev2 to detect faces.
    """
    # Import here to avoid circular imports
    from find_api.models.face import Face

    # Mock mode / Remote mode - skip face detection entirely
    # This keeps light/mock/remote mode working without downloading face models
    if current_ml_mode() != "full":
        logger.info("Non-full AI mode: skipping face detection for media %s", media_id)
        return 0

    # Real mode - run actual face detection
    try:
        logger.info("Running face detection for media %s...", media_id)
        from find_api.ml.face_detector import get_face_detector

        faces = get_face_detector().detect_faces(image)
        db.query(Face).filter(Face.media_id == media_id).delete(
            synchronize_session=False
        )

        if not faces:
            db.commit()
            return 0

        stored_count = 0
        for face_data in faces:
            bbox = face_data.get("bbox")
            embedding = face_data.get("embedding")
            confidence = face_data.get("confidence")
            if None in (bbox, embedding, confidence):
                continue

            db.add(
                Face(
                    media_id=media_id,
                    bounding_box=bbox,
                    embedding=embedding,
                    confidence=confidence,
                )
            )
            stored_count += 1

        db.commit()
        return stored_count
    except Exception:
        logger.exception("Face detection failed for media %s", media_id)
        db.rollback()
        return 0
