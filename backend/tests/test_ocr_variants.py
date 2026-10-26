"""Real-inference tests for the PP-OCRv5 mobile/server variant switch.

Everything here needs a working PaddleOCR install because it runs an actual
prediction -- hence the ``importorskip`` guard, which means the whole module
skips on `backend-check` (see issue #397).

The variant selection, cache-key, status-publishing, constructor-fallback, and
ModelManager failure-contract coverage that used to sit here needs no Paddle
runtime at all, so it lives in tests/test_ocr_logic.py and runs on every PR.
Add new cases there unless they genuinely require inference; a test parked in
this module is a test that does not run in CI.

Complements tests/test_ocr.py, which covers the core extract_text* API
contract -- see issue: "benchmark PP-OCRv5 mobile models for CPU deployments".
"""

import pytest

pytest.importorskip("paddleocr")
pytest.importorskip("paddle")

from find_api.core.model_manager import get_model_manager  # noqa: E402
from find_api.ml.ocr import OCRExtractor  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_model_manager():
    """Ensure each test starts from a clean ModelManager state."""
    get_model_manager().reset_for_tests()
    yield
    get_model_manager().reset_for_tests()


class TestVariantVisibility:
    """The active variant must be explicit in ModelManager status output --
    this is the issue's core acceptance criterion.
    """

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
