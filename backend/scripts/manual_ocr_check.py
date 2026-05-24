#!/usr/bin/env python3
"""
Manual OCR verification script - run with: python scripts/manual_ocr_check.py

Tests PaddleOCR 3.x API compatibility and basic functionality.
This is a standalone utility, not a pytest test.
"""

import sys
from pathlib import Path


def check_version():
    """Verify PaddleOCR version."""
    # pyrefly: ignore [missing-import]
    import paddleocr

    version = paddleocr.__version__
    print(f"✓ PaddleOCR version: {version}")
    if not version.startswith("3."):
        raise AssertionError(f"Expected PaddleOCR 3.x, got {version}")


def check_ocr_extractor(OCRExtractor, Image, np):
    """Test OCR extractor initialization and basic functionality."""
    print("\n--- Testing OCRExtractor ---")

    try:
        extractor = OCRExtractor()
        print("✓ OCRExtractor initialized")
    except Exception as e:
        print(f"✗ Failed to initialize OCRExtractor: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Create test image with text
    from PIL import ImageDraw

    test_image = Image.new("RGB", (200, 100), color="white")
    draw = ImageDraw.Draw(test_image)
    draw.text((10, 10), "TEST", fill="black")
    print("✓ Created test image with text")

    # Test extract_text with PIL Image
    try:
        result = extractor.extract_text(test_image)
        print(f"✓ extract_text(PIL Image) returned: {type(result).__name__}")
        assert isinstance(result, str), "extract_text should return string"
        assert "TEST" in result, "extract_text should find the text"
    except Exception as e:
        print(f"✗ extract_text failed: {e}")
        return False

    # Test extract_text with numpy array
    try:
        result = extractor.extract_text(np.array(test_image))
        print(f"✓ extract_text(numpy array) returned: {type(result).__name__}")
        assert isinstance(result, str), "extract_text should return string"
        assert "TEST" in result, "extract_text with numpy should find the text"
    except Exception as e:
        print(f"✗ extract_text with numpy failed: {e}")
        return False

    # Test extract_text_with_boxes
    try:
        result = extractor.extract_text_with_boxes(test_image)
        print(f"✓ extract_text_with_boxes returned: {type(result).__name__}")
        assert isinstance(result, list), "extract_text_with_boxes should return list"
        print(f"  Extracted {len(result)} text regions")
        assert len(result) > 0, "should extract at least one text region"
        for item in result:
            assert "text" in item and item["text"]
    except Exception as e:
        print(f"✗ extract_text_with_boxes failed: {e}")
        return False

    return True


if __name__ == "__main__":
    # Defer heavy imports to avoid issues during pytest collection
    from PIL import Image
    import numpy as np

    # Add src to path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from find_api.ml.ocr import OCRExtractor

    print("=" * 50)
    print("PaddleOCR 3.x Compatibility Test")
    print("=" * 50)

    try:
        check_version()
        success = check_ocr_extractor(OCRExtractor, Image, np)

        if success:
            print("\n" + "=" * 50)
            print("✓ All tests passed! PaddleOCR 3.x is working")
            print("=" * 50)
            sys.exit(0)
        else:
            print("\n✗ Some tests failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
