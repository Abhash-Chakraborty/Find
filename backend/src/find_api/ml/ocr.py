"""
OCR using PaddleOCR (CPU optimized).

The supported runtime is PaddleOCR 3.x with PaddlePaddle 3.2.x or 3.3.x.
PaddleOCR 3.x uses the ``predict`` API and pipeline flags such as
``use_textline_orientation``. A small PaddleOCR 2.x fallback remains so older
local environments fail less abruptly, but the lockfile should resolve the
current 3.x stack.

PaddlePaddle 3.3.1 regressed its oneDNN kernels and raises
``NotImplementedError`` on the first prediction, so ``_load_model`` probes once
after construction and reloads with ``enable_mkldnn=False`` when that happens.
See ``OCRExtractor._onednn_inference_works``.

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

There is deliberately no ``lang`` option. Pinning the variant requires passing
explicit ``text_detection_model_name``/``text_recognition_model_name``, and
PaddleOCR 3.x ignores ``lang`` whenever those are set -- it warns "`lang` and
`ocr_version` will be ignored when model names or model directories are not
`None`" and resolves the models purely from the given names. The pinned models
are the default unified PP-OCRv5 recognizers, which cover Simplified Chinese,
Traditional Chinese, Pinyin, English and Japanese. Supporting the ~106 other
PP-OCRv5 languages means selecting language-specific model names (e.g.
``korean_PP-OCRv5_mobile_rec``) rather than reintroducing ``lang``.
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

# Only used by the PaddleOCR 2.x fallback constructor below. 2.x has no
# mobile/server split and selects its models from `lang` alone; on the
# supported 3.x path the models are pinned by name instead (see module
# docstring for why there is no `lang` option).
LEGACY_FALLBACK_LANG = "en"


class OCRExtractor:
    """Extract text from images using PaddleOCR"""

    def __init__(self, variant: str | None = None):
        self.manager = get_model_manager()
        self.variant = self._normalize_variant(variant)
        # Variant-qualified cache key so ModelManager's own status output
        # (loaded_models / in_flight) makes the active variant visible
        # without any extra plumbing.
        self.model_name = f"paddleocr:{self.variant}"
        self.config_key = (
            f"paddleocr|variant={self.variant}|"
            "use_textline_orientation=True|use_gpu=False"
        )
        logger.info(
            "OCRExtractor initialized for PaddleOCR (CPU), variant=%s",
            self.variant,
        )

    @staticmethod
    def _normalize_variant(variant: Union[str, None]) -> str:
        resolved = settings.OCR_VARIANT if variant is None else variant
        if resolved not in VALID_VARIANTS:
            raise ValueError(
                f"Unknown OCR variant '{resolved}'. Expected one of {VALID_VARIANTS}."
            )
        return resolved

    def _construct(self, *, disable_onednn: bool = False):
        """Build a PaddleOCR pipeline, returning it plus whether 2.x was used."""
        model_names = PP_OCR_MODELS[self.variant]
        extra = {"enable_mkldnn": False} if disable_onednn else {}
        # PaddleOCR 3.x replaced the older use_angle_cls/use_gpu/show_log arguments
        # with pipeline-specific flags. Try the current API first, then fall back
        # for older 2.x installs. PaddleOCR 2.x has no mobile/server split, so
        # the requested variant only applies on the 3.x path.
        try:
            return (
                PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=True,
                    **model_names,
                    **extra,
                ),
                False,
            )
        except TypeError as exc:
            # Only a constructor signature mismatch means "this is really a 2.x
            # install". The lockfile pins paddleocr>=3.7, so a ValueError here
            # is a genuine model/config/download failure and must surface
            # instead of being masked by a legacy retry that silently ignores
            # the requested variant.
            logger.info("Falling back to PaddleOCR 2.x arguments: %s", exc)
            return (
                PaddleOCR(use_angle_cls=True, lang=LEGACY_FALLBACK_LANG, use_gpu=False),
                True,
            )

    @staticmethod
    def _onednn_inference_works(model) -> bool:
        """Run one tiny prediction to find out whether oneDNN kernels work here.

        PaddlePaddle 3.3.1 raises ``NotImplementedError`` from its oneDNN
        instruction path on the first real prediction --
        ``ConvertPirAttribute2RuntimeAttribute not support
        [pir::ArrayAttribute<pir::DoubleAttribute>]`` -- which takes down every
        OCR call in the container. PaddlePaddle 3.2.x is unaffected, so this is
        a version regression rather than a CPU-profile quirk, and it hits any
        image built from the current lock.

        The probe has to run an actual prediction because construction succeeds
        either way; there is no flag to interrogate. It costs one forward pass
        on a 32x32 blank image, once per load.
        """
        try:
            model.predict(np.zeros((32, 32, 3), dtype=np.uint8))
        except NotImplementedError:
            return False
        except Exception:  # noqa: BLE001 - any other failure is not what this
            # probe is testing for. Report the runtime as usable and let the
            # real call surface its own error rather than silently switching
            # kernels for an unrelated reason.
            return True
        return True

    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info("Loading PaddleOCR model (variant=%s)...", self.variant)

        model, legacy_api = self._construct()

        if not legacy_api and not self._onednn_inference_works(model):
            logger.warning(
                "PaddleOCR oneDNN kernels are unusable in this environment "
                "(known PaddlePaddle 3.3.x regression); reloading with "
                "enable_mkldnn=False. OCR will be slower but functional."
            )
            model, legacy_api = self._construct(disable_onednn=True)

        self._publish_variant_status(legacy_api=legacy_api)
        return model

    def _publish_variant_status(self, legacy_api: bool = False) -> None:
        """Make the active OCR variant explicit in ModelManager status output.

        Uses ``merge_runtime_status`` so the update happens under the manager
        lock: other ML components (CLIP/BLIP/YOLO) publish their own top-level
        keys into the same runtime status dict, and a read-modify-write from
        out here would race with them and silently drop their entries.

        ``legacy_api`` records that the PaddleOCR 2.x fallback constructor ran.
        2.x has no mobile/server split, so the requested variant was not
        actually applied and the status must not claim otherwise.
        """
        try:
            status = {
                "variant": self.variant,
                **PP_OCR_MODELS[self.variant],
            }
            if legacy_api:
                status["legacy_api"] = True
                status["variant_applied"] = False
            self.manager.merge_runtime_status("ocr", status)
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
