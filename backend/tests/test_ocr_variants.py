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

    @pytest.mark.parametrize("variant", ["mobile", "server"])
    def test_model_names_match_pp_ocrv5_variant(self, variant, monkeypatch):
        """_load_model must pin the variant's PP-OCRv5 det/rec model names.

        Asserting against PP_OCR_MODELS alone would just restate the table
        back to itself and still pass if _load_model ignored it, so this
        captures the kwargs PaddleOCR is actually constructed with.
        """
        captured = {}

        class _FakePaddleOCR:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr("find_api.ml.ocr.PaddleOCR", _FakePaddleOCR)

        extractor = OCRExtractor(variant=variant)
        extractor._load_model()

        assert captured["text_detection_model_name"] == f"PP-OCRv5_{variant}_det"
        assert captured["text_recognition_model_name"] == f"PP-OCRv5_{variant}_rec"
        # ...and that the table the rest of the code reads agrees.
        assert captured | PP_OCR_MODELS[extractor.variant] == captured


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

    def test_publishing_variant_does_not_clobber_other_runtime_status(self):
        """Status publishing must merge, not overwrite -- other ML components
        (CLIP/BLIP/YOLO) publish their own top-level keys into the same dict.
        """
        manager = get_model_manager()
        manager.set_runtime_status({"unrelated_component": {"loaded": True}})

        OCRExtractor(variant="mobile")._publish_variant_status()

        status = manager.get_status()
        assert status["runtime"]["unrelated_component"] == {"loaded": True}
        assert status["runtime"]["ocr"]["variant"] == "mobile"

    def test_legacy_fallback_is_flagged_in_status(self):
        """The 2.x fallback has no mobile/server split, so status must not
        claim the requested variant was applied.
        """
        OCRExtractor(variant="server")._publish_variant_status(legacy_api=True)

        ocr_status = get_model_manager().get_status()["runtime"]["ocr"]
        assert ocr_status["legacy_api"] is True
        assert ocr_status["variant_applied"] is False

    @pytest.mark.slow
    def test_loaded_variant_survives_real_inference(self):
        """End-to-end check that a real load publishes the variant block."""
        from PIL import Image

        manager = get_model_manager()
        manager.set_runtime_status({"unrelated_component": {"loaded": True}})

        extractor = OCRExtractor(variant="mobile")
        extractor.extract_text(Image.new("RGB", (32, 32), color="white"))

        status = manager.get_status()
        assert status["runtime"]["unrelated_component"] == {"loaded": True}
        assert status["runtime"]["ocr"]["variant"] == "mobile"


class TestFallbackAndErrorHandling:
    """A failed OCR model load must fail loudly and predictably, not
    silently degrade or crash the whole process.
    """

    def test_type_error_falls_back_to_legacy_signature(self, monkeypatch):
        """A TypeError means the installed PaddleOCR predates the 3.x
        keyword-only signature, which is the one case a legacy retry is
        the right answer.
        """
        calls = []

        def _fake_paddleocr(**kwargs):
            calls.append(kwargs)
            if "text_detection_model_name" in kwargs:
                raise TypeError("unexpected keyword argument")
            return object()

        monkeypatch.setattr("find_api.ml.ocr.PaddleOCR", _fake_paddleocr)

        OCRExtractor(variant="mobile")._load_model()

        assert len(calls) == 2
        assert calls[1] == {"use_angle_cls": True, "lang": "en", "use_gpu": False}

    def test_value_error_from_v3_is_not_masked_by_fallback(self, monkeypatch):
        """paddleocr>=3.7 is pinned, so a ValueError is a real model/config/
        download failure. Retrying the legacy signature would swallow it and
        load a model that ignores the requested variant.
        """
        calls = []

        def _fake_paddleocr(**kwargs):
            calls.append(kwargs)
            raise ValueError("No models are available for lang=None")

        monkeypatch.setattr("find_api.ml.ocr.PaddleOCR", _fake_paddleocr)

        with pytest.raises(ValueError, match="No models are available"):
            OCRExtractor(variant="mobile")._load_model()

        assert len(calls) == 1

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
        assert (
            server.model_name not in get_model_manager().get_status()["failed_models"]
        )
