"""Tests for GET /api/status/{job_id} — job status response shape."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestJobStatus:
    """Job status response shape for various states."""

    def _make_fake_job(self, **kwargs):
        job = MagicMock()
        for k, v in kwargs.items():
            setattr(job, k, v)
        return job

    @staticmethod
    def _patch_get_job(return_value=None, side_effect=None):
        return patch(
            "find_api.routers.status.get_job",
            return_value=return_value,
            side_effect=side_effect,
        )

    def test_queued_job(self, client):
        fake_job = self._make_fake_job(
            get_status=lambda: "queued",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            started_at=None,
            ended_at=None,
            completed_at=None,
            is_finished=False,
            is_failed=False,
            meta={},
            result=None,
            error_info=None,
        )

        with self._patch_get_job(return_value=fake_job):
            response = client.get("/api/status/some-job-id")

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "some-job-id"
        assert body["status"] == "queued"
        assert "created_at" in body
        assert "result" not in body
        assert "error" not in body

    def test_finished_job_includes_result(self, client):
        fake_job = self._make_fake_job(
            get_status=lambda: "finished",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            ended_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            completed_at=None,
            is_finished=True,
            is_failed=False,
            meta={},
            result={"media_id": 1},
            error_info=None,
        )

        with self._patch_get_job(return_value=fake_job):
            response = client.get("/api/status/done-job")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "finished"
        assert body["result"] == {"media_id": 1}

    def test_failed_job_includes_error(self, client):
        fake_job = self._make_fake_job(
            get_status=lambda: "failed",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            ended_at=datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
            completed_at=None,
            is_finished=False,
            is_failed=True,
            meta={"error": "Job failed"},
            result=None,
            error_info="RuntimeError: out of memory",
        )

        with self._patch_get_job(return_value=fake_job):
            response = client.get("/api/status/bad-job")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert "error" in body

    def test_unknown_job_returns_404(self, client):
        with self._patch_get_job(return_value=None):
            response = client.get("/api/status/nonexistent")

        assert response.status_code == 404


def test_loaded_models_endpoint(client):
    """Test the /api/status/models endpoint"""
    fake_redis = MagicMock()
    fake_redis.scan_iter.return_value = []
    fake_redis.get.return_value = None

    with (
        patch("find_api.routers.status.get_model_manager") as mock_get_manager,
        patch(
            "find_api.routers.status.get_redis_connection",
            return_value=fake_redis,
        ),
    ):
        mock_manager = mock_get_manager.return_value
        mock_manager.get_status.return_value = {
            "process": "api",
            "loaded_models": ["mock_test_model"],
            "in_flight": {},
            "failed_models": {},
            "max_loaded_models": 5,
            "updated_at": 0,
        }

        response = client.get("/api/status/models")

    assert response.status_code == 200
    body = response.json()
    assert "mock_test_model" in body["loaded_models"]
    assert body["processes"]["api"]["loaded_models"] == ["mock_test_model"]
    assert "ttl_seconds" in body


def test_loaded_models_endpoint_includes_worker_snapshot(client):
    """Test that worker-published model status is included."""
    worker_status = {
        "process": "worker",
        "loaded_models": ["siglip"],
        "in_flight": {},
        "failed_models": {"florence-2": {"error": "load failed", "failed_at": 0}},
        "max_loaded_models": 5,
        "updated_at": 0,
    }

    fake_redis = MagicMock()
    fake_redis.scan_iter.return_value = [b"find:model_status:worker"]
    fake_redis.get.return_value = json.dumps(worker_status)

    with (
        patch("find_api.routers.status.get_model_manager") as mock_get_manager,
        patch(
            "find_api.routers.status.get_redis_connection",
            return_value=fake_redis,
        ),
    ):
        mock_get_manager.return_value.get_status.return_value = {
            "process": "api",
            "loaded_models": [],
            "in_flight": {},
            "failed_models": {},
            "max_loaded_models": 5,
            "updated_at": 0,
        }

        response = client.get("/api/status/models")

    assert response.status_code == 200
    body = response.json()
    assert "siglip" in body["loaded_models"]
    assert (
        body["processes"]["worker"]["failed_models"]["florence-2"]["error"]
        == "load failed"
    )
