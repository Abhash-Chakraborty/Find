"""Tests for process-local ML model caching and failed-load handling."""

from datetime import datetime, timezone
import sys
import types

import pytest
from PIL import Image

from find_api.core.config import settings
from find_api.core.model_manager import (
    ModelLoadFailure,
    ModelManager,
    ModelUnavailableError,
)
from find_api.workers.processors import extract_image_metadata


@pytest.fixture()
def manager():
    model_manager = ModelManager()
    model_manager.clear()
    yield model_manager
    model_manager.clear()


def test_successful_model_loader_is_cached(manager):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return {"model": "ready"}

    assert manager.get_model("test-model", loader) == {"model": "ready"}
    assert manager.get_model("test-model", loader) == {"model": "ready"}
    assert calls["count"] == 1


def test_failed_model_loader_is_not_retried(manager):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        raise RuntimeError("simulated load failure")

    with pytest.raises(ModelUnavailableError) as first_error:
        manager.get_model("broken-model", loader)

    with pytest.raises(ModelUnavailableError) as second_error:
        manager.get_model("broken-model", loader)

    assert calls["count"] == 1
    assert first_error.value.name == "broken-model"
    assert second_error.value.name == "broken-model"
    assert manager.unavailable_models["broken-model"].error_type == "RuntimeError"


def test_clearing_model_failure_allows_retry(manager):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("first load failed")
        return "loaded"

    with pytest.raises(ModelUnavailableError):
        manager.get_model("retry-model", loader)

    manager.clear_model_failure("retry-model")

    assert manager.get_model("retry-model", loader) == "loaded"
    assert calls["count"] == 2


def test_clearing_multiple_model_failures_allows_retry(manager):
    def broken_loader():
        raise RuntimeError("load failed")

    with pytest.raises(ModelUnavailableError):
        manager.get_model("caption-model", broken_loader)
    with pytest.raises(ModelUnavailableError):
        manager.get_model("embedding-model", broken_loader)

    manager.clear_model_failures(("caption-model", "embedding-model"))

    assert "caption-model" not in manager.unavailable_models
    assert "embedding-model" not in manager.unavailable_models
    assert manager.failed_loads == {}


def test_config_key_change_allows_retry(manager):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("old config failed")
        return "loaded with new config"

    with pytest.raises(ModelUnavailableError):
        manager.get_model("config-model", loader, config_key="model=old")

    assert (
        manager.get_model("config-model", loader, config_key="model=new")
        == "loaded with new config"
    )
    assert calls["count"] == 2


def test_config_key_added_after_failure_allows_retry(manager):
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("missing config failed")
        return "loaded with config"

    with pytest.raises(ModelUnavailableError):
        manager.get_model("config-added-model", loader)

    assert (
        manager.get_model("config-added-model", loader, config_key="model=new")
        == "loaded with config"
    )
    assert calls["count"] == 2


def test_unavailable_stage_records_safe_metadata_and_continues(monkeypatch):
    monkeypatch.setattr(settings, "ML_MODE", "real")

    object_detector_module = types.ModuleType("find_api.ml.object_detector")
    captioner_module = types.ModuleType("find_api.ml.captioner")
    ocr_module = types.ModuleType("find_api.ml.ocr")

    class BrokenDetector:
        def detect(self, _image):
            failure = ModelLoadFailure(
                name="yolo",
                error_type="RuntimeError",
                reason="RuntimeError: simulated detector load failure",
                failed_at=datetime.now(timezone.utc),
            )
            raise ModelUnavailableError("yolo", failure)

    class Captioner:
        def generate_caption(self, _image):
            return "a generated caption"

    class OcrExtractor:
        def extract_text(self, _image):
            return "detected text"

        def extract_text_with_boxes(self, _image):
            return []

        def extract_text_and_boxes(self, _image):
            return "detected text", []

    object_detector_module.get_object_detector = lambda: BrokenDetector()
    captioner_module.get_image_captioner = lambda: Captioner()
    ocr_module.get_ocr_extractor = lambda: OcrExtractor()

    monkeypatch.setitem(
        sys.modules, "find_api.ml.object_detector", object_detector_module
    )
    monkeypatch.setitem(sys.modules, "find_api.ml.captioner", captioner_module)
    monkeypatch.setitem(sys.modules, "find_api.ml.ocr", ocr_module)

    metadata = extract_image_metadata(Image.new("RGB", (8, 8)))

    assert metadata["objects"] == []
    assert metadata["caption"] == "a generated caption"
    assert metadata["ocr_text"] == "detected text"
    assert set(metadata["stage_errors"]) == {"objects"}
    assert "Model 'yolo' is unavailable" in metadata["stage_errors"]["objects"]
