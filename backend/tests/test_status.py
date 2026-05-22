"""Tests for GET /api/status/{job_id} — job status response shape."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestJobStatus:
    """Job status response shape for various states."""

    def test_queued_job(self, client):
        fake_job = MagicMock()
        fake_job.get_status.return_value = "queued"
        fake_job.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fake_job.started_at = None
        fake_job.ended_at = None
        fake_job.is_finished = False
        fake_job.is_failed = False

        with patch("find_api.routers.status.Job.fetch", return_value=fake_job):
            response = client.get("/api/status/some-job-id")

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "some-job-id"
        assert body["status"] == "queued"
        assert "created_at" in body
        assert "result" not in body
        assert "error" not in body

    def test_finished_job_includes_result(self, client):
        fake_job = MagicMock()
        fake_job.get_status.return_value = "finished"
        fake_job.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fake_job.started_at = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        fake_job.ended_at = datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
        fake_job.is_finished = True
        fake_job.is_failed = False
        fake_job.result = {"media_id": 1}

        with patch("find_api.routers.status.Job.fetch", return_value=fake_job):
            response = client.get("/api/status/done-job")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "finished"
        assert body["result"] == {"media_id": 1}

    def test_failed_job_includes_error(self, client):
        fake_job = MagicMock()
        fake_job.get_status.return_value = "failed"
        fake_job.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fake_job.started_at = datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        fake_job.ended_at = datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc)
        fake_job.is_finished = False
        fake_job.is_failed = True
        fake_job.exc_info = "RuntimeError: out of memory"

        with patch("find_api.routers.status.Job.fetch", return_value=fake_job):
            response = client.get("/api/status/bad-job")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert "error" in body

    def test_unknown_job_returns_404(self, client):
        with patch(
            "find_api.routers.status.Job.fetch",
            side_effect=Exception("No such job"),
        ):
            response = client.get("/api/status/nonexistent")

        assert response.status_code == 404


def test_loaded_models_endpoint(client):
    """Test the /api/status/models endpoint"""
    with patch("find_api.routers.status.get_model_manager") as mock_get_manager:
        mock_manager = mock_get_manager.return_value
        mock_manager.get_loaded_models.return_value = ["mock_test_model"]

        response = client.get("/api/status/models")

    assert response.status_code == 200
    body = response.json()
    assert "mock_test_model" in body["loaded_models"]
    assert "ttl_seconds" in body
