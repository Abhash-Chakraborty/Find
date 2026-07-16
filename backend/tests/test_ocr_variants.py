"""Tests for PP-OCRv5 mobile/server variant selection and fallback behavior.

Complements tests/test_ocr.py (which covers the core extract_text* API
contract) with coverage specific to the mobile/server variant switch added
for CPU-deployment benchmarking -- see issue: "benchmark PP-OCRv5 mobile
models for CPU deployments".
"""

import pytest

pytest.importorskip("paddleocr")
pytest.importorskip("paddle")

from find_api.core.model_manager import (  # noqa: E402
    ModelUnavailableError,
    get_model_manager,
)
from find_api.ml.ocr import PP_OCR_MODELS, VALID_VARIANTS, OCRExtractor  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_model_manager():
    """Ensure each test starts from a clean ModelManager state."""
    get_model_manager().reset_for_tests()
    yield
    get_model_manager().reset_for_tests()


class TestVariantSelection:
    """Variant selection must be explicit and validated -- never silently
    default to whatever PaddleOCR itself would pick.
    """

    def test_valid_variants_are_mobile_and_server(self):
        assert set(VALID_VARIANTS) == {"mobile", "server"}

    def test_explicit_variant_is_used(self):
        extractor = OCRExtractor(variant="mobile")
        assert extractor.variant == "mobile"

        extractor = OCRExtractor(variant="server")
        assert extractor.variant == "server"

    def test_invalid_variant_raises(self):
        with pytest.raises(ValueError, match="Unknown OCR variant"):
            OCRExtractor(variant="ultra-fast-turbo")

    def test_variant_falls_back_to_settings_default(self):
        from find_api.core.config import settings

        extractor = OCRExtractor()
        assert extractor.variant == settings.OCR_VARIANT

    def test_model_names_match_pp_ocrv5_variant(self):
        mobile = OCRExtractor(variant="mobile")
        assert PP_OCR_MODELS["mobile"]["text_detection_model_name"] == "PP-OCRv5_mobile_det"
        assert PP_OCR_MODELS["mobile"]["text_recognition_model_name"] == "PP-OCRv5_mobile_rec"

        server = OCRExtractor(variant="server")
        assert PP_OCR_MODELS["server"]["text_detection_model_name"] == "PP-OCRv5_server_det"
        assert PP_OCR_MODELS["server"]["text_recognition_model_name"] == "PP-OCRv5_server_rec"


class TestVariantVisibility:
    """The active variant must be explicit in ModelManager status output --
    this is the issue's core acceptance criterion.
    """

    def test_variant_is_visible_in_cache_key(self):
        """Different variants must not collide in the ModelManager cache."""
        mobile = OCRExtractor(variant="mobile")
        server = OCRExtractor(variant="server")
        assert mobile.model_name != server.model_name
        assert "mobile" in mobile.model_name
        assert "server" in server.model_name

    @pytest.mark.slow
    def test_loaded_variant_appears_in_status(self):
        """After a real inference call, get_status() must show which
        variant is active -- both via loaded_models (cache key) and via
        the runtime.ocr status block.
        """
        from PIL import Image

        extractor = OCRExtractor(variant="mobile")
        extractor.extract_text(Image.new("RGB", (32, 32), color="white"))

        status = get_model_manager().get_status()
        assert "paddleocr:mobile" in status["loaded_models"]
        assert status["runtime"]["ocr"]["variant"] == "mobile"

    @pytest.mark.slow
    def test_switching_variant_does_not_clobber_other_runtime_status(self):
        """set_runtime_status must merge, not overwrite -- other ML
        components (CLIP/BLIP/YOLO) may publish through the same call.
        """
        manager = get_model_manager()
        manager.set_runtime_status({"unrelated_component": {"loaded": True}})

        from PIL import Image

        extractor = OCRExtractor(variant="mobile")
        extractor.extract_text(Image.new("RGB", (32, 32), color="white"))

        status = manager.get_status()
        assert status["runtime"]["unrelated_component"] == {"loaded": True}
        assert status["runtime"]["ocr"]["variant"] == "mobile"


class TestFallbackAndErrorHandling:
    """A failed OCR model load must fail loudly and predictably, not
    silently degrade or crash the whole process.
    """

    def test_unavailable_model_raises_model_unavailable_error(self, monkeypatch):
        """Simulate a load failure (e.g. corrupt cache, network failure on
        first download) and confirm it surfaces as ModelUnavailableError,
        matching the contract other ML components in ModelManager rely on.
        """
        extractor = OCRExtractor(variant="mobile")

        def _boom():
            raise RuntimeError("simulated model download failure")

        monkeypatch.setattr(extractor, "_load_model", _boom)

        from PIL import Image

        with pytest.raises(ModelUnavailableError):
            extractor.extract_text(Image.new("RGB", (32, 32), color="white"))

    def test_failed_model_is_recorded_in_status(self, monkeypatch):
        extractor = OCRExtractor(variant="mobile")

        def _boom():
            raise RuntimeError("simulated model download failure")

        monkeypatch.setattr(extractor, "_load_model", _boom)

        from PIL import Image

        with pytest.raises(ModelUnavailableError):
            extractor.extract_text(Image.new("RGB", (32, 32), color="white"))

        status = get_model_manager().get_status()
        assert "paddleocr:mobile" in status["failed_models"]

    def test_changing_variant_allows_retry_after_failure(self, monkeypatch):
        """A failure on one variant must not block the other variant --
        they're independent cache entries (config_key differs), so
        switching should retry cleanly rather than raising the cached
        failure from a different variant.
        """
        mobile = OCRExtractor(variant="mobile")

        def _boom():
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(mobile, "_load_model", _boom)

        from PIL import Image

        with pytest.raises(ModelUnavailableError):
            mobile.extract_text(Image.new("RGB", (32, 32), color="white"))

        # A fresh server-variant extractor uses a different cache key/model
        # name, so it must not be affected by the mobile-variant failure.
        server = OCRExtractor(variant="server")
        assert server.model_name != mobile.model_name
        assert server.model_name not in get_model_manager().get_status()["failed_models"]