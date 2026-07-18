"""
Tests for the remote ML client.
"""

import io
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from find_api.ml.remote_client import (
    RemoteMLAuthError, _feature_enabled, _strip_exif,
    check_health, remote_analyze, remote_cluster, remote_embed,
)

def _rgb_image(width: int = 16, height: int = 16) -> Image.Image:
    return Image.new("RGB", (width, height), color=(42, 42, 42))

def _mock_settings(url="http://local:8001", key="secret", strip=True, features="embed,caption,detect,ocr,cluster"):
    s = MagicMock()
    s.REMOTE_ML_URL = url
    s.REMOTE_ML_API_KEY = key
    s.REMOTE_ML_STRIP_EXIF = strip
    s.REMOTE_ML_FEATURES = features
    return s

class TestExifStripping:
    def test_strip_exif_returns_bytes(self):
        result = _strip_exif(_rgb_image())
        assert isinstance(result, bytes)
        assert b"\xff\xe1" not in result  # No EXIF APP1 marker

class TestFeatureEnabled:
    def test_enabled_feature(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings(features="embed,caption"))
        assert _feature_enabled("embed") is True
        assert _feature_enabled("ocr") is False

class TestCheckHealth:
    def test_health_success(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings())

        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.get.return_value.status_code = 200
            mock_client.get.return_value.json.return_value = {"status": "ok", "ml_mode": "full"}
            result = check_health()
        assert result["status"] == "ok"

class TestRemoteAnalyze:
    def test_analyze_success(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings())

        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"caption": "a cat"}
            mock_resp.raise_for_status.return_value = None
            mock_client.post.return_value = mock_resp
            result = remote_analyze(_rgb_image())
        assert result["caption"] == "a cat"

    def test_analyze_401_raises_auth_error(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings())

        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_client.post.return_value.status_code = 401
            with pytest.raises(RemoteMLAuthError):
                remote_analyze(_rgb_image())

class TestRemoteEmbed:
    def test_embed_success(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings())

        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"embedding": [0.5] * 768}
            mock_resp.raise_for_status.return_value = None
            mock_client.post.return_value = mock_resp
            result = remote_embed(_rgb_image(), {"caption": "test"})
        assert len(result) == 768

class TestRemoteCluster:
    def test_cluster_success(self, monkeypatch):
        import find_api.ml.remote_client as rc
        monkeypatch.setattr(rc, "settings", _mock_settings())

        with patch("httpx.Client") as mock_cls:
            mock_client = mock_cls.return_value.__enter__.return_value
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"labels": [0, 0]}
            mock_resp.raise_for_status.return_value = None
            mock_client.post.return_value = mock_resp
            result = remote_cluster([[0.1, 0.2], [0.3, 0.4]])
        assert result["labels"] == [0, 0]
