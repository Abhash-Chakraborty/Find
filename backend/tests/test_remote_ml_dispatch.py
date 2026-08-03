"""Remote mode must actually reach the remote client.

These cover the seams between "remote is configured" and "the remote call
happens", which is where this feature was previously broken: resolve_runtime()
mapped remote to "unavailable", so every applied_mode guard fired and the
dispatch code in processors.py/jobs.py was unreachable.
"""

import types
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
        with (
            patch("find_api.ml.remote_client.remote_analyze", fake),
            patch("find_api.ml.remote_client._feature_enabled", lambda f: True),
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
        with (
            patch("find_api.ml.remote_client.remote_analyze", fake),
            patch("find_api.ml.remote_client._feature_enabled", lambda f: False),
        ):
            result = processors.extract_image_metadata(_rgb_image())

        assert fake.call_count == 0
        assert result["stage_status"]["ocr"]["status"] == "skipped"

    def test_remote_mode_calls_remote_embed(self, monkeypatch):
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        fake = MagicMock(return_value=[0.1] * 768)
        with (
            patch("find_api.ml.remote_client.remote_embed", fake),
            patch("find_api.ml.remote_client._feature_enabled", lambda f: True),
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

        with (
            patch("find_api.ml.remote_client.remote_cluster", fake),
            patch("find_api.ml.remote_client._feature_enabled", lambda f: True),
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

        with (
            patch("find_api.ml.remote_client.remote_cluster", fake_remote),
            patch("find_api.ml.remote_client._feature_enabled", lambda f: False),
            patch("find_api.ml.clusterer.get_image_clusterer", lambda: fake_local),
        ):
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


class TestFeatureContractIsHonoured:
    """REMOTE_ML_FEATURES has to bind end to end. Checking it only on the
    client while the server runs every stage would make it cosmetic: turning
    OCR off would still have the remote host OCR the image.
    """

    def test_enabled_features_are_sent_to_the_server(self, monkeypatch):
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        fake = MagicMock(return_value={"caption": "x"})
        with (
            patch("find_api.ml.remote_client.remote_analyze", fake),
            patch(
                "find_api.ml.remote_client._feature_enabled",
                lambda f: f in {"caption", "detect"},
            ),
        ):
            result = processors.extract_image_metadata(_rgb_image())

        assert sorted(fake.call_args.kwargs["features"]) == ["caption", "detect"]
        # A stage that never ran must not be reported as success.
        assert result["stage_status"]["ocr"]["status"] == "skipped"

    def test_server_runs_only_requested_stages(self, monkeypatch):
        """extract_image_metadata(stages=...) must not invoke skipped stages."""
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "full")

        detector = MagicMock()
        detector.detect.return_value = []
        stub = types.ModuleType("find_api.ml.object_detector")
        stub.get_object_detector = lambda: detector

        with patch.dict("sys.modules", {"find_api.ml.object_detector": stub}):
            metadata = processors.extract_image_metadata(
                _rgb_image(), stages={"detect"}
            )

        assert detector.detect.call_count == 1
        assert metadata["stage_status"]["object_detection"]["status"] == "success"
        assert metadata["stage_status"]["captioning"]["status"] == "skipped"
        assert metadata["stage_status"]["ocr"]["status"] == "skipped"


class TestDisabledEmbeddingIsNotPersistedAsMock:
    def test_disabled_embed_raises_rather_than_returning_a_mock_vector(
        self, monkeypatch
    ):
        """A mock vector in the real vector column is searchable and always
        wrong, so the disabled path must be explicit instead.
        """
        monkeypatch.setattr(processors, "current_ml_mode", lambda: "remote")

        with (
            patch("find_api.ml.remote_client._feature_enabled", lambda f: False),
            pytest.raises(processors.RemoteFeatureDisabled),
        ):
            processors.generate_hybrid_embedding(_rgb_image(), {})


class TestClusterInputValidation:
    """The endpoint takes an embedding matrix straight off the network."""

    @pytest.mark.parametrize(
        "embeddings",
        [
            None,
            [],
            [[0.1, 0.2], [0.3]],  # ragged
            [[0.1, "x"]],  # non-numeric
            [[float("nan"), 0.1]],  # non-finite
            [0.1, 0.2],  # not a matrix
        ],
    )
    def test_invalid_matrices_are_rejected(self, embeddings):
        from find_api.ml.clusterer import (
            InvalidEmbeddingMatrix,
            validate_embedding_matrix,
        )

        with pytest.raises(InvalidEmbeddingMatrix):
            validate_embedding_matrix(embeddings, expected_dim=2)

    def test_point_limit_is_enforced(self):
        from find_api.ml import clusterer

        with patch.object(clusterer, "MAX_REMOTE_CLUSTER_POINTS", 3):
            with pytest.raises(clusterer.InvalidEmbeddingMatrix, match="limit"):
                clusterer.validate_embedding_matrix([[0.1]] * 4)

    def test_wrong_dimension_is_rejected(self):
        from find_api.ml.clusterer import (
            InvalidEmbeddingMatrix,
            validate_embedding_matrix,
        )

        with pytest.raises(InvalidEmbeddingMatrix, match="dimension"):
            validate_embedding_matrix([[0.1, 0.2]], expected_dim=768)

    def test_valid_matrix_passes(self):
        from find_api.ml.clusterer import validate_embedding_matrix

        matrix = validate_embedding_matrix([[0.1, 0.2], [0.3, 0.4]], expected_dim=2)
        assert matrix.shape == (2, 2)
