"""
Image processing utilities for worker jobs
"""

import logging
import numpy as np
from PIL import Image
from typing import Dict, Any, List

from app.ml.object_detector import get_object_detector
from app.ml.captioner import get_image_captioner
from app.ml.ocr import get_ocr_extractor
from app.ml.clip_embedder import get_clip_embedder

logger = logging.getLogger(__name__)


def extract_image_metadata(image: Image.Image) -> Dict[str, Any]:
    """
    Run all ML models to extract metadata from image
    """
    metadata = {}

    # 1. Object Detection
    try:
        logger.info("Running object detection...")
        detector = get_object_detector()
        objects = detector.detect(image)
        metadata["objects"] = objects
        logger.info(f"Detected {len(objects)} objects")
    except Exception as e:
        logger.error(f"Object detection failed: {e}")
        metadata["objects"] = []

    # 2. Image Captioning
    try:
        logger.info("Generating caption...")
        captioner = get_image_captioner()
        caption = captioner.generate_caption(image)
        metadata["caption"] = caption
        logger.info(f"Caption: {caption}")
    except Exception as e:
        logger.error(f"Captioning failed: {e}")
        metadata["caption"] = ""

    # 3. OCR Text Extraction
    try:
        logger.info("Extracting text...")
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
    try:
        logger.info("Generating CLIP embedding...")
        embedder = get_clip_embedder()

        # Generate Image Embedding
        image_embedding = embedder.embed_image(image)

        # Generate Caption Embedding
        caption_embedding = embedder.embed_text(metadata.get("caption", ""))

        # Generate Objects Embedding
        objects = metadata.get("objects", [])
        object_names = [obj["class"] for obj in objects]
        if object_names:
            objects_text = "detected objects: " + ", ".join(
                sorted(list(set(object_names)))
            )
        else:
            objects_text = ""
        objects_embedding = embedder.embed_text(objects_text)

        # Create Hybrid Vector (Average)
        hybrid_vector = (image_embedding + caption_embedding + objects_embedding) / 3.0

        # Normalize
        hybrid_vector = hybrid_vector / np.linalg.norm(hybrid_vector)

        logger.info("Hybrid embedding generated")
        return hybrid_vector.tolist()

    except Exception as e:
        logger.error(f"CLIP embedding failed: {e}")
        raise
