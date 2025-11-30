"""
OCR using PaddleOCR (CPU optimized)
"""

from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging

from app.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract text from images using PaddleOCR"""

    def __init__(self):
        self.manager = get_model_manager()
        logger.info("OCRExtractor initialized for PaddleOCR (CPU)")

    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info("Loading PaddleOCR model...")
        # Force CPU to save VRAM for other models
        ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
        return ocr

    def extract_text(self, image: Union[Image.Image, np.ndarray]) -> str:
        """
        Extract all text from image as a single string
        """
        try:
            if isinstance(image, Image.Image):
                image = np.array(image)

            # PaddleOCR expects BGR or RGB? It handles numpy arrays.
            # Standard cv2 is BGR, PIL is RGB. PaddleOCR handles both but prefers RGB usually?
            # Let's assume RGB from PIL -> numpy is fine.

            ocr = self.manager.get_model("paddleocr", self._load_model)

            result = ocr.ocr(image, cls=True)

            text_parts = []
            if result and result[0]:
                for line in result[0]:
                    text_parts.append(line[1][0])

            full_text = "\n".join(text_parts)
            logger.info(f"Extracted {len(full_text)} characters")
            return full_text

        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            raise

    def extract_text_with_boxes(
        self, image: Union[Image.Image, np.ndarray]
    ) -> List[Dict]:
        """
        Extract text with bounding boxes
        """
        try:
            if isinstance(image, Image.Image):
                image = np.array(image)

            ocr = self.manager.get_model("paddleocr", self._load_model)

            result = ocr.ocr(image, cls=True)

            blocks = []
            if result and result[0]:
                for line in result[0]:
                    box = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    text = line[1][0]
                    confidence = line[1][1]

                    # Convert box to x1, y1, x2, y2
                    x_coords = [p[0] for p in box]
                    y_coords = [p[1] for p in box]

                    blocks.append(
                        {
                            "text": text,
                            "confidence": float(confidence),
                            "bbox": {
                                "x1": float(min(x_coords)),
                                "y1": float(min(y_coords)),
                                "x2": float(max(x_coords)),
                                "y2": float(max(y_coords)),
                            },
                        }
                    )

            return blocks

        except Exception as e:
            logger.error(f"Failed to extract text blocks: {e}")
            raise


# Global instance
_ocr_extractor = None


def get_ocr_extractor() -> OCRExtractor:
    """Get or create global OCR extractor instance"""
    global _ocr_extractor
    if _ocr_extractor is None:
        _ocr_extractor = OCRExtractor()
    return _ocr_extractor
