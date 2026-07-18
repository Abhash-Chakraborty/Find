"""Test PaddleOCR integration and version compatibility."""

from PIL import Image, ImageDraw
import numpy as np
import pytest

# Skip entire module if optional ML dependencies aren't installed
pytest.importorskip("paddleocr")
pytest.importorskip("paddle")

from find_api.ml.ocr import OCRExtractor  # noqa: E402


@pytest.fixture
def ocr_extractor():
    """Initialize OCR extractor."""
    # Let initialization errors fail the test (don't silently skip)
    # since we already have pytest.importorskip guards at module level
    return OCRExtractor()


@pytest.fixture
def simple_image():
    """Create a simple test image (100x100 with white background)."""
    img = Image.new("RGB", (100, 100), color="white")
    return img


@pytest.fixture
def image_with_text():
    """Create an image with simple text using PIL ImageDraw."""
    img = Image.new("RGB", (320, 140), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((24, 48), "HELLO FIND", fill="black")
    return img


class TestOCRExtractor:
    """Test OCR functionality with the supported PaddleOCR stack."""

    def test_extractor_initializes(self, ocr_extractor):
        """Test that OCRExtractor initializes without errors."""
        assert ocr_extractor is not None
        assert ocr_extractor.manager is not None

    def test_extract_text_returns_string(self, ocr_extractor, simple_image):
        """Test extract_text returns a string."""
        result = ocr_extractor.extract_text(simple_image)
        assert isinstance(result, str)

    def test_extract_text_accepts_pil_image(self, ocr_extractor, simple_image):
        """Test extract_text accepts PIL Image objects."""
        # Should not raise an exception
        result = ocr_extractor.extract_text(simple_image)
        assert isinstance(result, str)

    def test_extract_text_accepts_numpy_array(self, ocr_extractor, simple_image):
        """Test extract_text accepts numpy arrays."""
        image_array = np.array(simple_image)
        result = ocr_extractor.extract_text(image_array)
        assert isinstance(result, str)

    def test_extract_text_with_boxes_returns_list(self, ocr_extractor, simple_image):
        """Test extract_text_with_boxes returns a list of dicts."""
        result = ocr_extractor.extract_text_with_boxes(simple_image)
        assert isinstance(result, list)

    def test_extract_text_with_boxes_dict_structure(
        self, ocr_extractor, image_with_text
    ):
        """Test extract_text_with_boxes returns dicts with correct structure."""
        result = ocr_extractor.extract_text_with_boxes(image_with_text)

        # Result should be a list
        assert isinstance(result, list)

        assert result, "OCR should return at least one block for the text image"

        for item in result:
            assert isinstance(item, dict)
            assert "text" in item
            assert "confidence" in item
            assert "bbox" in item
            assert isinstance(item["text"], str)
            assert isinstance(item["confidence"], float)

            # bbox should have coordinates
            bbox = item["bbox"]
            assert "x1" in bbox
            assert "y1" in bbox
            assert "x2" in bbox
            assert "y2" in bbox
            assert all(isinstance(v, (int, float)) for v in bbox.values())

    def test_extract_text_and_boxes_runs_inference_once(
        self, ocr_extractor, simple_image, monkeypatch
    ):
        """The combined method should run the OCR model a single time."""
        calls = {"count": 0}
        original_run = ocr_extractor._run_ocr

        def _counting_run(ocr, image):
            calls["count"] += 1
            return original_run(ocr, image)

        monkeypatch.setattr(ocr_extractor, "_run_ocr", _counting_run)

        text, blocks = ocr_extractor.extract_text_and_boxes(simple_image)

        assert calls["count"] == 1
        assert isinstance(text, str)
        assert isinstance(blocks, list)

    @pytest.mark.slow
    def test_paddleocr_api_compatibility(self, ocr_extractor, image_with_text):
        """Test that the supported PaddleOCR stack is usable through the public API.

        Marked as slow because this exercises real PaddleOCR initialization,
        which may download model weights on first run (slow/non-hermetic).
        Skip in fast test runs with: pytest -m "not slow"
        """
        result = ocr_extractor.extract_text(image_with_text)
        assert isinstance(result, str)
        assert result.strip(), "OCR should extract text from image with text"
        assert "HELLO" in result.upper()


class TestOCRErrorHandling:
    """Test error handling in OCR extraction."""

    def test_extract_text_handles_invalid_image(self, ocr_extractor):
        """Test the extractor has a deterministic contract for tiny images."""
        img = Image.new("RGB", (1, 1))
        result = ocr_extractor.extract_text(img)
        assert isinstance(result, str)
