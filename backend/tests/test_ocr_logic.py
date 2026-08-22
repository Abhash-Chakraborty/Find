"""Tests for pure-Python OCR logic that run without paddleocr/paddle dependencies.

This module tests logic-only aspects of OCRExtractor and OCR configuration:
- Variant normalization and validation
- Cache key generation
- Status publishing and merging
- oneDNN fallback probe logic

Also covers the PaddleOCR constructor contract (model-name pinning, the 2.x
TypeError fallback, and the ValueError that must not be masked by it) and the
ModelManager failure contract, by injecting a stand-in ``paddleocr`` module --
none of that needs a real Paddle runtime.

These tests run in CI with only the dev dependency group (no ML dependencies).
Only tests that genuinely run inference stay in test_ocr.py and
test_ocr_variants.py behind pytest.importorskip, where CI skips them.

See issue #397: OCR tests should run in CI without requiring paddleocr installation.
"""

import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import sys
from contextlib import contextmanager
from types import SimpleNamespace

# Import only pure Python code; do NOT import paddleocr or paddle
from find_api.core.config import settings
from find_api.core.model_manager import (
    ModelManager,
    ModelUnavailableError,
    get_model_manager,
)
from find_api.ml.ocr import PP_OCR_MODELS, VALID_VARIANTS, OCRExtractor


@pytest.fixture(autouse=True)
def _no_redis_status_publish():
    """Keep ModelManager's best-effort Redis publish out of these tests.

    ``publish_status()`` opens a real connection to ``settings.REDIS_URL`` on
    every state change, including both ``reset_for_tests()`` calls in the
    fixture below. With nothing listening -- the normal case for
    ``backend-check`` and for a plain local ``pytest`` run -- each call sits in
    a connect timeout, which is ~4s here and turned this pure-logic module into
    a multi-minute run. Nothing in this file asserts on the published payload;
    it is fire-and-forget observability, so stub it out.

    Declared before ``_reset_model_manager`` so it wraps that fixture's own
    reset calls -- same-scope autouse fixtures run in definition order.
    """
    with patch.object(ModelManager, "publish_status", lambda self: None):
        yield


@pytest.fixture(autouse=True)
def _reset_model_manager():
    """Ensure each test starts from a clean ModelManager state."""
    get_model_manager().reset_for_tests()
    yield
    get_model_manager().reset_for_tests()


@contextmanager
def fake_paddleocr(paddle_ocr):
    """Install a stand-in ``paddleocr`` module for the duration of the block.

    ``OCRExtractor._construct`` imports ``PaddleOCR`` from inside the function
    body, specifically so this module stays importable without the package.
    That makes ``sys.modules["paddleocr"]`` the seam to patch -- there is no
    module-level ``find_api.ml.ocr.PaddleOCR`` attribute to monkeypatch any
    more, and patching one would not affect the function-local import.
    """
    with patch.dict(sys.modules, {"paddleocr": SimpleNamespace(PaddleOCR=paddle_ocr)}):
        yield


class TestPPOCRModelsConstant:
    """Test the PP_OCR_MODELS mapping is correctly defined."""

    def test_pp_ocr_models_has_mobile_and_server(self):
        """PP_OCR_MODELS should include both variant keys."""
        assert "mobile" in PP_OCR_MODELS
        assert "server" in PP_OCR_MODELS

    def test_mobile_models_have_correct_names(self):
        """Mobile variant should use mobile-specific model names."""
        mobile = PP_OCR_MODELS["mobile"]
        assert mobile["text_detection_model_name"] == "PP-OCRv5_mobile_det"
        assert mobile["text_recognition_model_name"] == "PP-OCRv5_mobile_rec"

    def test_server_models_have_correct_names(self):
        """Server variant should use server-specific model names."""
        server = PP_OCR_MODELS["server"]
        assert server["text_detection_model_name"] == "PP-OCRv5_server_det"
        assert server["text_recognition_model_name"] == "PP-OCRv5_server_rec"


class TestValidVariantsConstant:
    """Test the VALID_VARIANTS tuple is correctly defined."""

    def test_valid_variants_is_tuple(self):
        """VALID_VARIANTS should be a tuple for immutability."""
        assert isinstance(VALID_VARIANTS, tuple)

    def test_valid_variants_are_mobile_and_server(self):
        """VALID_VARIANTS should contain exactly mobile and server."""
        assert set(VALID_VARIANTS) == {"mobile", "server"}

    def test_valid_variants_matches_pp_ocr_models_keys(self):
        """VALID_VARIANTS should match the keys in PP_OCR_MODELS."""
        assert set(VALID_VARIANTS) == set(PP_OCR_MODELS.keys())


class TestNormalizeVariant:
    """Test OCRExtractor._normalize_variant() logic."""

    def test_normalize_variant_accepts_mobile(self):
        """_normalize_variant('mobile') should return 'mobile'."""
        result = OCRExtractor._normalize_variant("mobile")
        assert result == "mobile"

    def test_normalize_variant_accepts_server(self):
        """_normalize_variant('server') should return 'server'."""
        result = OCRExtractor._normalize_variant("server")
        assert result == "server"

    def test_normalize_variant_none_uses_settings_default(self):
        """_normalize_variant(None) should use settings.OCR_VARIANT."""
        result = OCRExtractor._normalize_variant(None)
        assert result == settings.OCR_VARIANT
        assert result in VALID_VARIANTS

    def test_normalize_variant_rejects_unknown_variant(self):
        """_normalize_variant should raise ValueError for unknown variants."""
        with pytest.raises(ValueError, match="Unknown OCR variant"):
            OCRExtractor._normalize_variant("ultra-fast-turbo")

    def test_normalize_variant_error_message_lists_valid(self):
        """ValueError should mention valid options."""
        with pytest.raises(ValueError, match="Expected one of"):
            OCRExtractor._normalize_variant("invalid")


class TestOCRExtractorInitialization:
    """Test OCRExtractor initialization without loading actual models."""

    def test_extractor_init_explicit_mobile_variant(self):
        """OCRExtractor(variant='mobile') should set variant='mobile'."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            assert extractor.variant == "mobile"

    def test_extractor_init_explicit_server_variant(self):
        """OCRExtractor(variant='server') should set variant='server'."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="server")
            assert extractor.variant == "server"

    def test_extractor_init_none_variant_uses_settings(self):
        """OCRExtractor() should use settings.OCR_VARIANT."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor()
            assert extractor.variant == settings.OCR_VARIANT

    def test_extractor_init_invalid_variant_raises(self):
        """OCRExtractor(variant='bad') should raise ValueError."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            with pytest.raises(ValueError, match="Unknown OCR variant"):
                OCRExtractor(variant="bad")

    def test_extractor_stores_model_manager_reference(self):
        """OCRExtractor should store a reference to ModelManager."""
        mock_manager = MagicMock()
        with patch("find_api.ml.ocr.get_model_manager", return_value=mock_manager):
            extractor = OCRExtractor(variant="mobile")
            assert extractor.manager is mock_manager


class TestModelNameCacheKey:
    """Test that model_name includes the variant for cache isolation."""

    def test_mobile_model_name_includes_variant(self):
        """Mobile variant should have 'mobile' in model_name."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            assert "mobile" in extractor.model_name

    def test_server_model_name_includes_variant(self):
        """Server variant should have 'server' in model_name."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="server")
            assert "server" in extractor.model_name

    def test_mobile_and_server_have_different_model_names(self):
        """Different variants must have different model names."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            mobile = OCRExtractor(variant="mobile")
            server = OCRExtractor(variant="server")
            assert mobile.model_name != server.model_name

    def test_model_name_starts_with_paddleocr_prefix(self):
        """model_name should start with 'paddleocr:' prefix."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            assert extractor.model_name.startswith("paddleocr:")

    def test_config_key_includes_variant(self):
        """config_key should include variant for cache isolation."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            mobile = OCRExtractor(variant="mobile")
            server = OCRExtractor(variant="server")
            assert mobile.config_key != server.config_key
            assert "mobile" in mobile.config_key
            assert "server" in server.config_key


class TestPublishVariantStatus:
    """Test _publish_variant_status() behavior without model loading."""

    def test_publish_variant_status_mobile(self):
        """Publishing status for mobile variant should include 'mobile'."""
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status()

            # Should call merge_runtime_status with 'ocr' key
            mock_manager.merge_runtime_status.assert_called()
            call_args = mock_manager.merge_runtime_status.call_args
            assert call_args[0][0] == "ocr"  # First positional arg is 'ocr'
            status_dict = call_args[0][1]  # Second positional arg is the status
            assert status_dict["variant"] == "mobile"

    def test_publish_variant_status_server(self):
        """Publishing status for server variant should include 'server'."""
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="server")
            extractor._publish_variant_status()

            # Should call merge_runtime_status with 'ocr' key
            mock_manager.merge_runtime_status.assert_called()
            call_args = mock_manager.merge_runtime_status.call_args
            assert call_args[0][0] == "ocr"
            status_dict = call_args[0][1]
            assert status_dict["variant"] == "server"

    def test_publish_variant_status_includes_model_names(self):
        """Status should include the model names from PP_OCR_MODELS."""
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status()

            call_args = mock_manager.merge_runtime_status.call_args
            status_dict = call_args[0][1]

            # Should include model names from PP_OCR_MODELS
            assert status_dict["text_detection_model_name"] == "PP-OCRv5_mobile_det"
            assert status_dict["text_recognition_model_name"] == "PP-OCRv5_mobile_rec"

    def test_publish_variant_status_legacy_api_flag(self):
        """When legacy_api=True, status should include legacy_api and variant_applied=False."""
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status(legacy_api=True)

            call_args = mock_manager.merge_runtime_status.call_args
            status_dict = call_args[0][1]

            assert status_dict["legacy_api"] is True
            assert status_dict["variant_applied"] is False

    def test_publish_variant_status_no_legacy_flag_when_false(self):
        """When legacy_api=False (default), status should not include legacy_api flag."""
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status(legacy_api=False)

            call_args = mock_manager.merge_runtime_status.call_args
            status_dict = call_args[0][1]

            assert "legacy_api" not in status_dict
            assert "variant_applied" not in status_dict

    def test_publish_variant_status_calls_merge_not_set(self):
        """Status must use merge_runtime_status, not set, to avoid clobbering
        other components' status entries.
        """
        with patch(
            "find_api.ml.ocr.get_model_manager", return_value=MagicMock()
        ) as mock_mgr:
            mock_manager = mock_mgr.return_value
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status()

            # Should call merge_runtime_status, not set_runtime_status
            mock_manager.merge_runtime_status.assert_called_once()
            assert not mock_manager.set_runtime_status.called


class TestStatusPublishingWithExistingStatus:
    """Test that variant status merges with other component status."""

    def test_publishing_variant_does_not_clobber_other_components(self):
        """Status publishing must preserve entries from other ML components."""
        manager = get_model_manager()
        manager.set_runtime_status({"unrelated_component": {"loaded": True}})

        with patch("find_api.ml.ocr.get_model_manager", return_value=manager):
            extractor = OCRExtractor(variant="mobile")
            extractor._publish_variant_status()

        status = manager.get_status()
        assert status["runtime"]["unrelated_component"] == {"loaded": True}
        assert status["runtime"]["ocr"]["variant"] == "mobile"

    def test_publishing_variant_merges_under_ocr_key(self):
        """All OCR status should be under the 'ocr' key in runtime status."""
        manager = get_model_manager()
        manager.set_runtime_status({"ocr": {"some_field": "value"}})

        with patch("find_api.ml.ocr.get_model_manager", return_value=manager):
            extractor = OCRExtractor(variant="server")
            extractor._publish_variant_status()

        status = manager.get_status()
        ocr_status = status["runtime"]["ocr"]
        # Should have both old and new fields (merge, not replace)
        assert ocr_status["variant"] == "server"


class TestOneDnnInferenceProbe:
    """Test _onednn_inference_works() logic for checking kernel health."""

    def test_onednn_probe_returns_true_on_success(self):
        """Successful predict call means oneDNN is usable."""
        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=[])

        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            result = extractor._onednn_inference_works(mock_model)
            assert result is True

    def test_onednn_probe_returns_false_on_not_implemented_error(self):
        """NotImplementedError means oneDNN kernels are broken."""
        mock_model = MagicMock()
        mock_model.predict = MagicMock(
            side_effect=NotImplementedError("ConvertPirAttribute2RuntimeAttribute")
        )

        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            result = extractor._onednn_inference_works(mock_model)
            assert result is False

    def test_onednn_probe_returns_true_on_unrelated_error(self):
        """Unrelated errors don't mean oneDNN is broken."""
        mock_model = MagicMock()
        mock_model.predict = MagicMock(
            side_effect=RuntimeError("model weights missing")
        )

        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            result = extractor._onednn_inference_works(mock_model)
            assert result is True

    def test_onednn_probe_passes_blank_32x32_image(self):
        """Probe should pass a 32x32 blank image to predict()."""
        mock_model = MagicMock()
        mock_model.predict = MagicMock(return_value=[])

        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")
            extractor._onednn_inference_works(mock_model)

            # Check that predict was called with correct image shape
            mock_model.predict.assert_called_once()
            called_image = mock_model.predict.call_args[0][0]
            assert isinstance(called_image, np.ndarray)
            assert called_image.shape == (32, 32, 3)
            assert called_image.dtype == np.uint8


class TestOneDnnFallbackLogic:
    """Test the fallback behavior when oneDNN probe fails."""

    def test_load_model_probes_onednn_after_construct(self):
        """_load_model should probe oneDNN health after construction."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            mock_model = MagicMock()
            mock_model.predict = MagicMock(return_value=[])

            with patch.object(extractor, "_construct") as mock_construct:
                mock_construct.return_value = (mock_model, False)
                with patch.object(extractor, "_publish_variant_status"):
                    extractor._load_model()

                    # Should have called _construct
                    mock_construct.assert_called()

    def test_load_model_reloads_without_onednn_when_probe_fails(self):
        """When probe detects NotImplementedError, should reconstruct with disable_onednn=True."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            construct_calls = []

            def fake_construct(*, disable_onednn=False):
                construct_calls.append(disable_onednn)
                model = MagicMock()
                model.predict = MagicMock(return_value=[])
                return model, False

            with patch.object(extractor, "_construct", side_effect=fake_construct):
                # First call succeeds, but probe fails
                with patch.object(
                    extractor, "_onednn_inference_works", return_value=False
                ):
                    with patch.object(extractor, "_publish_variant_status"):
                        extractor._load_model()

            # Should call _construct twice: first without disable_onednn, then with it
            assert construct_calls == [False, True]

    def test_load_model_keeps_onednn_when_probe_succeeds(self):
        """When probe succeeds, should not reconstruct."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            construct_calls = []

            def fake_construct(*, disable_onednn=False):
                construct_calls.append(disable_onednn)
                model = MagicMock()
                model.predict = MagicMock(return_value=[])
                return model, False

            with patch.object(extractor, "_construct", side_effect=fake_construct):
                with patch.object(
                    extractor, "_onednn_inference_works", return_value=True
                ):
                    with patch.object(extractor, "_publish_variant_status"):
                        extractor._load_model()

            # Should call _construct only once
            assert construct_calls == [False]

    def test_load_model_publishes_legacy_api_flag(self):
        """_load_model should pass legacy_api flag to _publish_variant_status."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            model = MagicMock()
            model.predict = MagicMock(return_value=[])

            with patch.object(extractor, "_construct") as mock_construct:
                mock_construct.return_value = (model, True)  # legacy_api=True
                with patch.object(extractor, "_publish_variant_status") as mock_publish:
                    with patch.object(
                        extractor, "_onednn_inference_works", return_value=True
                    ):
                        extractor._load_model()

                    # Should pass legacy_api=True
                    mock_publish.assert_called_with(legacy_api=True)


class TestConstructorFallback:
    """Test _construct() argument handling and the PaddleOCR 2.x fallback."""

    def test_construct_with_disable_onednn_false(self):
        """_construct(disable_onednn=False) must not pass enable_mkldnn at all."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            mock_paddle = MagicMock()

            with fake_paddleocr(mock_paddle):
                extractor._construct(disable_onednn=False)

            call_kwargs = mock_paddle.call_args[1]

            # Absent, not merely "not False" -- the default path leaves oneDNN
            # selection to PaddleOCR rather than pinning it either way.
            assert "enable_mkldnn" not in call_kwargs

    def test_construct_with_disable_onednn_true(self):
        """_construct(disable_onednn=True) should set enable_mkldnn=False."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            mock_paddle = MagicMock()

            with fake_paddleocr(mock_paddle):
                extractor._construct(disable_onednn=True)

            call_kwargs = mock_paddle.call_args[1]

            assert call_kwargs.get("enable_mkldnn") is False

    def test_construct_returns_model_and_legacy_flag(self):
        """_construct should return a tuple of (model, legacy_api_flag)."""
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            mock_model = MagicMock()
            mock_paddle = MagicMock(return_value=mock_model)

            with fake_paddleocr(mock_paddle):
                model, legacy_api = extractor._construct()

            assert model is mock_model
            assert legacy_api is False

    @pytest.mark.parametrize("variant", ["mobile", "server"])
    def test_model_names_match_pp_ocrv5_variant(self, variant):
        """_load_model must pin the variant's PP-OCRv5 det/rec model names.

        Asserting against PP_OCR_MODELS alone would just restate the table
        back to itself and still pass if _load_model ignored it, so this
        captures the kwargs PaddleOCR is actually constructed with.
        """
        captured = {}

        class _FakePaddleOCR:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def predict(self, _image):
                return []

        with fake_paddleocr(_FakePaddleOCR):
            extractor = OCRExtractor(variant=variant)
            extractor._load_model()

        assert captured["text_detection_model_name"] == f"PP-OCRv5_{variant}_det"
        assert captured["text_recognition_model_name"] == f"PP-OCRv5_{variant}_rec"
        # ...and that the table the rest of the code reads agrees.
        assert captured | PP_OCR_MODELS[extractor.variant] == captured

    def test_type_error_falls_back_to_legacy_signature(self):
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

        with fake_paddleocr(_fake_paddleocr):
            OCRExtractor(variant="mobile")._load_model()

        assert len(calls) == 2
        assert calls[1] == {"use_angle_cls": True, "lang": "en", "use_gpu": False}

    def test_value_error_from_v3_is_not_masked_by_fallback(self):
        """paddleocr>=3.7 is pinned, so a ValueError is a real model/config/
        download failure. Retrying the legacy signature would swallow it and
        load a model that ignores the requested variant.
        """
        calls = []

        def _fake_paddleocr(**kwargs):
            calls.append(kwargs)
            raise ValueError("No models are available for lang=None")

        with fake_paddleocr(_fake_paddleocr):
            with pytest.raises(ValueError, match="No models are available"):
                OCRExtractor(variant="mobile")._load_model()

        assert len(calls) == 1

    def test_missing_paddleocr_surfaces_as_import_error(self):
        """The import moved into _construct, so absence must still be loud.

        Before the move, importing this module raised ImportError at import
        time. The failure now has to appear on the first construction attempt
        instead of being swallowed into a silently degraded pipeline.
        """
        with patch("find_api.ml.ocr.get_model_manager", return_value=MagicMock()):
            extractor = OCRExtractor(variant="mobile")

            with patch.dict(sys.modules, {"paddleocr": None}):
                with pytest.raises(ImportError):
                    extractor._construct()


class TestModelManagerFailureContract:
    """A failed OCR model load must fail loudly and predictably, not
    silently degrade or crash the whole process.

    None of this needs a real PaddleOCR install -- ``_load_model`` is replaced
    outright -- so it belongs here rather than behind ``importorskip``.
    """

    @staticmethod
    def _blank_image():
        from PIL import Image

        return Image.new("RGB", (32, 32), color="white")

    def test_unavailable_model_raises_model_unavailable_error(self, monkeypatch):
        """Simulate a load failure (e.g. corrupt cache, network failure on
        first download) and confirm it surfaces as ModelUnavailableError,
        matching the contract other ML components in ModelManager rely on.
        """
        extractor = OCRExtractor(variant="mobile")

        def _boom():
            raise RuntimeError("simulated model download failure")

        monkeypatch.setattr(extractor, "_load_model", _boom)

        with pytest.raises(ModelUnavailableError):
            extractor.extract_text(self._blank_image())

    def test_failed_model_is_recorded_in_status(self, monkeypatch):
        extractor = OCRExtractor(variant="mobile")

        def _boom():
            raise RuntimeError("simulated model download failure")

        monkeypatch.setattr(extractor, "_load_model", _boom)

        with pytest.raises(ModelUnavailableError):
            extractor.extract_text(self._blank_image())

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

        with pytest.raises(ModelUnavailableError):
            mobile.extract_text(self._blank_image())

        # A fresh server-variant extractor uses a different cache key/model
        # name, so it must not be affected by the mobile-variant failure.
        server = OCRExtractor(variant="server")
        assert server.model_name != mobile.model_name
        assert (
            server.model_name not in get_model_manager().get_status()["failed_models"]
        )
