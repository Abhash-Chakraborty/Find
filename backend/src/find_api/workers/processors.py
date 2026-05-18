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

logger = logging.getLogger(__name__)


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
        }

    metadata = {}

    # 1. Object Detection
    try:
        if on_stage:
            on_stage("detecting objects")
        logger.info("Running object detection...")
        from find_api.ml.object_detector import get_object_detector

        detector = get_object_detector()
        objects = detector.detect(image)
        metadata["objects"] = objects
        logger.info(f"Detected {len(objects)} objects")
    except Exception as e:
        logger.error(f"Object detection failed: {e}")
        metadata["objects"] = []

    # 2. Image Captioning
    try:
        if on_stage:
            on_stage("generating caption")
        logger.info("Generating caption...")
        from find_api.ml.captioner import get_image_captioner

        captioner = get_image_captioner()
        caption = captioner.generate_caption(image)
        metadata["caption"] = caption
        logger.info(f"Caption: {caption}")
    except Exception as e:
        logger.error(f"Captioning failed: {e}")
        metadata["caption"] = ""

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
        logger.info(f"Extracted {len(ocr_text)} characters")
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        metadata["ocr_text"] = ""
        metadata["text_blocks"] = []

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

    except Exception as e:
        logger.error(f"CLIP embedding failed: {e}")
        raise
