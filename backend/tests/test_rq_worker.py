"""Tests for RQ worker startup observability."""

from unittest.mock import MagicMock, Mock, patch

from find_api.workers.rq_worker import initialize_worker_observability


def test_worker_publishes_runtime_before_first_job():
    manager = Mock()
    session = Mock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = session
    preferences = Mock()
    runtime = Mock()
    runtime.to_worker_status.return_value = {"applied_mode": "full"}

    with (
        patch(
            "find_api.workers.rq_worker.get_model_manager",
            return_value=manager,
        ),
        patch("find_api.workers.rq_worker.SessionLocal", session_factory),
        patch(
            "find_api.workers.rq_worker.load_runtime_preferences",
            return_value=preferences,
        ),
        patch(
            "find_api.workers.rq_worker.resolve_runtime",
            return_value=runtime,
        ),
    ):
        initialize_worker_observability()

    manager.start_autocleanup.assert_called_once()
    manager.set_runtime_status.assert_called_once_with({"applied_mode": "full"})
