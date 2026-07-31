"""Remote mode must actually reach the remote client.

These cover the seams between "remote is configured" and "the remote call
happens", which is where this feature was previously broken: resolve_runtime()
mapped remote to "unavailable", so every applied_mode guard fired and the
dispatch code in processors.py/jobs.py was unreachable.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from find_api.workers import jobs, processors


def _rgb_image() -> Image.Image:
    return Image.new("RGB", (16, 16), color=(10, 20, 30))


class TestAnalyzeDispatch:
    def test_remote_mode_calls_remote_analyze(self, monkeypatch):
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        fake = MagicMock(
            return_value={"caption": "a bike", "objects": [], "ocr_text": ""}
        )
        with patch("find_api.ml.remote_client.remote_analyze", fake), patch(
            "find_api.ml.remote_client._feature_enabled", lambda f: True
        ):
            result = processors.extract_image_metadata(_rgb_image())

        assert fake.call_count == 1
        assert result["caption"] == "a bike"
        # The remote server may omit stage_status; callers rely on it existing.
        assert set(result["stage_status"]) >= {"object_detection", "captioning", "ocr"}

    def test_remote_mode_skips_transmission_when_no_features_enabled(self, monkeypatch):
        """Nothing may leave the machine when every analyze feature is off."""
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        fake = MagicMock()
        with patch("find_api.ml.remote_client.remote_analyze", fake), patch(
            "find_api.ml.remote_client._feature_enabled", lambda f: False
        ):
            result = processors.extract_image_metadata(_rgb_image())

        assert fake.call_count == 0
        assert result["stage_status"]["ocr"]["status"] == "skipped"

    def test_remote_mode_calls_remote_embed(self, monkeypatch):
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        fake = MagicMock(return_value=[0.1] * 768)
        with patch("find_api.ml.remote_client.remote_embed", fake), patch(
            "find_api.ml.remote_client._feature_enabled", lambda f: True
        ):
            vector = processors.generate_hybrid_embedding(_rgb_image(), {})

        assert fake.call_count == 1
        assert len(vector) == 768


class TestFaceDetectionStaysLocal:
    def test_remote_mode_never_transmits_faces(self, monkeypatch):
        """Biometric data is deliberately not offloaded -- there is no remote
        face endpoint, and faces are the last thing that should leave the box.
        """
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        assert processors.detect_and_store_faces(_rgb_image(), 1, MagicMock()) == 0


class TestClusterDispatch:
    def test_remote_cluster_is_dispatched(self):
        """`cluster` ships enabled by default, so it must actually dispatch."""
        embeddings = np.eye(4, dtype=np.float32)
        fake = MagicMock(return_value={"labels": [0, 0, 1, 1], "info": {"n": 4}})

        with patch("find_api.ml.remote_client.remote_cluster", fake), patch(
            "find_api.ml.remote_client._feature_enabled", lambda f: True
        ):
            labels, info = jobs._remote_cluster_embeddings(embeddings)

        assert fake.call_count == 1
        # Embeddings must be JSON-serializable, not raw numpy.
        sent = fake.call_args[0][0]
        assert isinstance(sent, list) and isinstance(sent[0], list)
        assert all(isinstance(v, float) for v in sent[0])
        assert labels.tolist() == [0, 0, 1, 1]
        assert info == {"n": 4}

    def test_disabled_cluster_feature_falls_back_to_local(self):
        embeddings = np.eye(4, dtype=np.float32)
        fake_remote = MagicMock()
        fake_local = MagicMock()
        fake_local.cluster.return_value = (np.array([-1, -1, -1, -1]), {})

        with patch("find_api.ml.remote_client.remote_cluster", fake_remote), patch(
            "find_api.ml.remote_client._feature_enabled", lambda f: False
        ), patch("find_api.ml.clusterer.get_image_clusterer", lambda: fake_local):
            jobs._remote_cluster_embeddings(embeddings)

        assert fake_remote.call_count == 0
        assert fake_local.cluster.call_count == 1


class TestCentroidsWithoutSklearn:
    def test_compute_centroids_does_not_need_sklearn(self):
        """Remote mode computes centroids locally from remote labels, on hosts
        that may not ship scikit-learn -- so this path must stay import-free.
        """
        from find_api.ml.clusterer import get_image_clusterer

        embeddings = np.array(
            [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]], dtype=np.float32
        )
        labels = np.array([0, 0, 1, 1], dtype=np.int32)

        with patch.dict("sys.modules", {"sklearn.cluster": None}):
            centroids = get_image_clusterer().compute_centroids(embeddings, labels)

        assert set(centroids) == {0, 1}
        assert pytest.approx(float(np.linalg.norm(centroids[0])), abs=1e-5) == 1.0
