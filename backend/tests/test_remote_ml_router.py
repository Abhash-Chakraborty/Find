"""
Tests for /api/ml/ endpoints.
"""

import io
import json
import types
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# Generated per run rather than committed as a literal. A hardcoded string of
# this shape trips the secret scanner that gates every PR, and these tests only
# need the fixture and the request headers to agree on some value.
VALID_TOKEN = f"pytest-remote-ml-{uuid4().hex}"
AUTH = {"Authorization": f"Bearer {VALID_TOKEN}"}
WRONG_AUTH = {"Authorization": "Bearer wrong-token"}


@pytest.fixture()
def client_with_key(monkeypatch):
    from find_api.core import config as cfg_module

    mock_settings = MagicMock()
    mock_settings.ML_MODE = "full"
    mock_settings.REMOTE_ML_API_KEY = VALID_TOKEN
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


class TestEmbedTextEndpoint:
    """Search in remote mode depends on this endpoint, so it carries the same
    auth contract as the other protected routes.
    """

    def test_embed_text_requires_auth(self, client_with_key):
        response = client_with_key.post("/api/ml/embed_text", json={"text": "hello"})
        assert response.status_code == 401

    def test_embed_text_rejects_wrong_token(self, client_with_key):
        response = client_with_key.post(
            "/api/ml/embed_text", json={"text": "hello"}, headers=WRONG_AUTH
        )
        assert response.status_code == 401

    def test_embed_text_rejects_empty_text(self, client_with_key):
        response = client_with_key.post(
            "/api/ml/embed_text", json={"text": "   "}, headers=AUTH
        )
        assert response.status_code == 422

    def test_embed_text_returns_embedding(self, client_with_key):
        fake = MagicMock()
        fake.embed_text.return_value = [0.5] * 768

        # clip_embedder pulls in torch, which the mock test env does not ship,
        # so stub the whole module rather than patching an attribute on it.
        stub = types.ModuleType("find_api.ml.clip_embedder")
        stub.get_clip_embedder = lambda: fake

        with patch.dict("sys.modules", {"find_api.ml.clip_embedder": stub}):
            response = client_with_key.post(
                "/api/ml/embed_text", json={"text": "a red bicycle"}, headers=AUTH
            )

        assert response.status_code == 200
        assert len(response.json()["embedding"]) == 768
        fake.embed_text.assert_called_once_with("a red bicycle")
