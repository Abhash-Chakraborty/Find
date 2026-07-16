"""
OCR using PaddleOCR (CPU optimized).

The supported runtime is PaddleOCR 3.x with PaddlePaddle 3.2.x. PaddleOCR 3.x
uses the ``predict`` API and pipeline flags such as
``use_textline_orientation``. A small PaddleOCR 2.x fallback remains so older
local environments fail less abruptly, but the lockfile should resolve the
current 3.x stack.

PP-OCRv5 ships two hardware-targeted variants for both the detection and
recognition models:

- ``server``: heavier, higher-accuracy models tuned for GPU/high-throughput
  deployments. This is PaddleOCR's own default when no model name is given,
  which previously made the active variant invisible in this file.
- ``mobile``: lightweight models tuned for CPU-only, resource-constrained
  deployments (smaller download, faster load, lower peak RAM).

The active variant is controlled by ``settings.OCR_VARIANT`` (or an explicit
constructor argument) and is always made explicit -- both in this module via
``PP_OCR_MODELS`` and in ModelManager status output via
``OCRExtractor._publish_variant_status``.
"""

from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging

from find_api.core.config import settings
from find_api.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)

# Explicit PP-OCRv5 model names per variant. PaddleOCR silently defaults to
# the server variant when these are omitted, so we always pass them.
PP_OCR_MODELS = {
    "mobile": {
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "text_recognition_model_name": "PP-OCRv5_mobile_rec",
    },
    "server": {
        "text_detection_model_name": "PP-OCRv5_server_det",
        "text_recognition_model_name": "PP-OCRv5_server_rec",
    },
}

VALID_VARIANTS = tuple(PP_OCR_MODELS)


class OCRExtractor:
    """Extract text from images using PaddleOCR"""

    def __init__(self, variant: str | None = None, lang: str = "en"):
        self.manager = get_model_manager()
        self.variant = self._normalize_variant(variant)
        self.lang = lang
        # Variant-qualified cache key so ModelManager's own status output
        # (loaded_models / in_flight) makes the active variant visible
        # without any extra plumbing.
        self.model_name = f"paddleocr:{self.variant}"
        self.config_key = (
            f"paddleocr|variant={self.variant}|lang={self.lang}|"
            "use_angle_cls=True|use_gpu=False"
        )
        logger.info(
            "OCRExtractor initialized for PaddleOCR (CPU), variant=%s lang=%s",
            self.variant,
            self.lang,
        )

    @staticmethod
    def _normalize_variant(variant: Union[str, None]) -> str:
        resolved = variant or settings.OCR_VARIANT
        if resolved not in VALID_VARIANTS:
            raise ValueError(
                f"Unknown OCR variant '{resolved}'. Expected one of {VALID_VARIANTS}."
            )
        return resolved

    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info("Loading PaddleOCR model (variant=%s)...", self.variant)
        model_names = PP_OCR_MODELS[self.variant]
        # PaddleOCR 3.x replaced the older use_angle_cls/use_gpu/show_log arguments
        # with pipeline-specific flags. Try the current API first, then fall back
        # for older 2.x installs. PaddleOCR 2.x has no mobile/server split, so
        # the requested variant only applies on the 3.x path.
        try:
            model = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                **model_names,
            )
        except (TypeError, ValueError) as exc:
            logger.info("Falling back to PaddleOCR 2.x arguments: %s", exc)
            model = PaddleOCR(use_angle_cls=True, lang=self.lang, use_gpu=False)

        self._publish_variant_status()
        return model

    def _publish_variant_status(self) -> None:
        """Make the active OCR variant explicit in ModelManager status output.

        Merges into any existing runtime status dict instead of overwriting
        it outright, since other ML components (CLIP/BLIP/YOLO) may also
        publish entries through the same ``set_runtime_status`` call.
        """
        try:
            current = self.manager.get_status().get("runtime") or {}
            merged = dict(current)
            merged["ocr"] = {
                "variant": self.variant,
                "lang": self.lang,
                **PP_OCR_MODELS[self.variant],
            }
            self.manager.set_runtime_status(merged)
        except Exception as exc:
            # Status publishing is best-effort observability, never fatal.
            logger.debug("Failed to publish OCR variant status: %s", exc)

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

            with self.manager.use_model(
                self.model_name, self._load_model, config_key=self.config_key
            ) as ocr:
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

            with self.manager.use_model(
                self.model_name, self._load_model, config_key=self.config_key
            ) as ocr:
                result = self._run_ocr(ocr, image)

            return self._extract_blocks(result)

        except Exception as e:
            logger.error(f"Failed to extract text blocks: {e}")
            raise

    def extract_text_and_boxes(
        self, image: Union[Image.Image, np.ndarray]
    ) -> tuple[str, List[Dict]]:
        """Extract joined text and text blocks from a single OCR pass.

        Equivalent to calling extract_text() and extract_text_with_boxes()
        but runs the (expensive) model inference only once.
        """
        try:
            if isinstance(image, Image.Image):
                image = np.array(image)

            with self.manager.use_model(
                self.model_name, self._load_model, config_key=self.config_key
            ) as ocr:
                result = self._run_ocr(ocr, image)

            full_text = "\n".join(self._extract_text_parts(result))
            blocks = self._extract_blocks(result)
            logger.info(f"Extracted {len(full_text)} characters")
            return full_text, blocks

        except Exception as e:
            logger.error(f"Failed to extract text and boxes: {e}")
            raise


# Global instance
_ocr_extractor = None


def get_ocr_extractor() -> OCRExtractor:
    """Get or create global OCR extractor instance"""
    global _ocr_extractor
    if _ocr_extractor is None:
        _ocr_extractor = OCRExtractor()
    return _ocr_extractor