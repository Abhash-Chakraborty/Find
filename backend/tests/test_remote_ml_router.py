"""
Tests for /api/ml/ endpoints.
"""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client_with_key(monkeypatch):
    from find_api.core import config as cfg_module

    mock_settings = MagicMock()
    mock_settings.ML_MODE = "full"
    mock_settings.REMOTE_ML_API_KEY = "test-secret-token-abc123"
    mock_settings.MIN_CLUSTER_SIZE = 2
    mock_settings.MIN_SAMPLES = 1
    monkeypatch.setattr(cfg_module, "settings", mock_settings)

    import find_api.routers.ml as ml_mod

    monkeypatch.setattr(ml_mod, "settings", mock_settings)

    from fastapi import FastAPI
    from find_api.routers.ml import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture()
def client_no_key(monkeypatch):
    from find_api.core import config as cfg_module

    mock_settings = MagicMock()
    mock_settings.ML_MODE = "full"
    mock_settings.REMOTE_ML_API_KEY = ""
    mock_settings.MIN_CLUSTER_SIZE = 2
    mock_settings.MIN_SAMPLES = 1
    monkeypatch.setattr(cfg_module, "settings", mock_settings)

    import find_api.routers.ml as ml_mod

    monkeypatch.setattr(ml_mod, "settings", mock_settings)

    from fastapi import FastAPI
    from find_api.routers.ml import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_jpeg_bytes(width: int = 8, height: int = 8) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


VALID_TOKEN = "test-secret-token-abc123"
AUTH = {"Authorization": f"Bearer {VALID_TOKEN}"}
WRONG_AUTH = {"Authorization": "Bearer wrong-token"}


class TestHealthEndpoint:
    def test_health_returns_ok(self, client_with_key):
        resp = client_with_key.get("/api/ml/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_when_no_key_configured(self, client_no_key):
        resp = client_no_key.get("/api/ml/health")
        assert resp.status_code == 200


class TestAuthRejection:
    @pytest.mark.parametrize("endpoint", ["/api/ml/analyze", "/api/ml/embed"])
    def test_missing_auth_returns_401(self, client_with_key, endpoint):
        jpeg = _make_jpeg_bytes()
        resp = client_with_key.post(
            endpoint, files={"image": ("img.jpg", jpeg, "image/jpeg")}
        )
        assert resp.status_code == 401

    @pytest.mark.parametrize("endpoint", ["/api/ml/analyze", "/api/ml/embed"])
    def test_wrong_token_returns_401(self, client_with_key, endpoint):
        jpeg = _make_jpeg_bytes()
        resp = client_with_key.post(
            endpoint,
            headers=WRONG_AUTH,
            files={"image": ("img.jpg", jpeg, "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_cluster_missing_auth_returns_401(self, client_with_key):
        resp = client_with_key.post(
            "/api/ml/cluster", json={"embeddings": [[0.1, 0.2]]}
        )
        assert resp.status_code == 401


class TestMockedInference:
    def test_analyze_returns_expected_shape(self, client_with_key):
        mock_result = {
            "caption": "a test image",
            "objects": [{"class": "cat", "confidence": 0.9}],
            "ocr_text": "hello",
            "text_blocks": [],
            "stage_status": {},
        }
        with patch(
            "find_api.workers.processors.extract_image_metadata",
            return_value=mock_result,
        ):
            resp = client_with_key.post(
                "/api/ml/analyze",
                headers=AUTH,
                files={"image": ("img.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200
        assert resp.json()["caption"] == "a test image"

    def test_embed_returns_vector(self, client_with_key):
        with patch(
            "find_api.workers.processors.generate_hybrid_embedding",
            return_value=[0.1] * 768,
        ):
            resp = client_with_key.post(
                "/api/ml/embed",
                headers=AUTH,
                files={"image": ("img.jpg", _make_jpeg_bytes(), "image/jpeg")},
                data={"metadata": json.dumps({"caption": "test"})},
            )
        assert resp.status_code == 200
        assert len(resp.json()["embedding"]) == 768

    def test_cluster_returns_labels(self, client_with_key):
        embeddings = [[1.0, 0.0], [1.0, 0.1], [-1.0, 0.0], [-1.0, 0.1]]
        resp = client_with_key.post(
            "/api/ml/cluster", headers=AUTH, json={"embeddings": embeddings}
        )
        assert resp.status_code == 200
        assert "labels" in resp.json()


class TestTransportErrors:
    def test_analyze_ml_failure_returns_500(self, client_with_key):
        with patch(
            "find_api.workers.processors.extract_image_metadata",
            side_effect=RuntimeError("error"),
        ):
            resp = client_with_key.post(
                "/api/ml/analyze",
                headers=AUTH,
                files={"image": ("img.jpg", _make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 500
