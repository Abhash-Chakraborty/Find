"""
OCR using PaddleOCR (CPU optimized).

The supported runtime is PaddleOCR 3.x with PaddlePaddle 3.2.x. PaddleOCR 3.x
uses the ``predict`` API and pipeline flags such as
``use_textline_orientation``. A small PaddleOCR 2.x fallback remains so older
local environments fail less abruptly, but the lockfile should resolve the
current 3.x stack.
"""

from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging

from find_api.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract text from images using PaddleOCR"""

    def __init__(self):
        self.manager = get_model_manager()
        logger.info("OCRExtractor initialized for PaddleOCR (CPU)")

    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info("Loading PaddleOCR model...")
        # PaddleOCR 3.x replaced the older use_angle_cls/use_gpu/show_log arguments
        # with pipeline-specific flags. Try the current API first, then fall back
        # for older 2.x installs.
        try:
            return PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        except (TypeError, ValueError) as exc:
            logger.info("Falling back to PaddleOCR 2.x arguments: %s", exc)
            return PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)

    def _run_ocr(self, ocr, image: np.ndarray):
        """Run OCR through the current PaddleOCR API."""
        if hasattr(ocr, "predict"):
            return ocr.predict(
                image,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        return ocr.ocr(image, cls=True)

    def _extract_text_parts(self, result) -> List[str]:
        """Normalize PaddleOCR 2.x/3.x output into plain text lines."""
        if not result:
            return []

        text_parts: List[str] = []
        for page in result:
            if isinstance(page, dict) and "rec_texts" in page:
                text_parts.extend(str(text) for text in page.get("rec_texts", []))
                continue

            if hasattr(page, "json") and isinstance(page.json, dict):
                texts = page.json.get("res", {}).get("rec_texts", [])
                text_parts.extend(str(text) for text in texts)
                continue

            if isinstance(page, list):
                for line in page:
                    if len(line) >= 2 and isinstance(line[1], (list, tuple)):
                        text_parts.append(str(line[1][0]))

        return [text for text in text_parts if text]

    def _extract_blocks(self, result) -> List[Dict]:
        """Normalize PaddleOCR 2.x/3.x output into text blocks with boxes."""
        if not result:
            return []

        blocks = []
        for page in result:
            if isinstance(page, dict) and "rec_texts" in page:
                texts = page.get("rec_texts", [])
                scores = page.get("rec_scores", [])
                boxes = page.get("rec_boxes")
                if boxes is None:
                    boxes = page.get("dt_polys")
                if boxes is None:
                    boxes = []
                for text, score, box in zip(texts, scores, boxes):
                    blocks.append(self._make_block(text, score, box))
                continue

            if hasattr(page, "json") and isinstance(page.json, dict):
                data = page.json.get("res", {})
                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])
                boxes = data.get("rec_boxes")
                if boxes is None:
                    boxes = data.get("dt_polys")
                if boxes is None:
                    boxes = []
                for text, score, box in zip(texts, scores, boxes):
                    blocks.append(self._make_block(text, score, box))
                continue

            if isinstance(page, list):
                for line in page:
                    if len(line) >= 2 and isinstance(line[1], (list, tuple)):
                        blocks.append(self._make_block(line[1][0], line[1][1], line[0]))

        return blocks

    def _make_block(self, text, confidence, box) -> Dict:
        """Create a stable OCR block shape from a polygon or rectangle."""
        coords = np.array(box, dtype=float)
        if coords.ndim == 1 and coords.size >= 4:
            x1, y1, x2, y2 = coords[:4]
        else:
            coords = coords.reshape(-1, 2)
            x1 = float(coords[:, 0].min())
            y1 = float(coords[:, 1].min())
            x2 = float(coords[:, 0].max())
            y2 = float(coords[:, 1].max())

        return {
            "text": str(text),
            "confidence": float(confidence),
            "bbox": {
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
            },
        }

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

            with self.manager.use_model("paddleocr", self._load_model) as ocr:
                result = self._run_ocr(ocr, image)

            full_text = "\n".join(self._extract_text_parts(result))
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

            with self.manager.use_model("paddleocr", self._load_model) as ocr:
                result = self._run_ocr(ocr, image)

            return self._extract_blocks(result)

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
