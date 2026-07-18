"""RQ worker integration for idle health and applied-runtime reporting."""

import logging
from typing import Any

from rq.worker import SimpleWorker

from find_api.core.config import settings
from find_api.core.database import SessionLocal
from find_api.core.model_manager import get_model_manager
from find_api.core.runtime_profile import load_runtime_preferences, resolve_runtime

logger = logging.getLogger(__name__)


def initialize_worker_observability() -> None:
    """Publish worker health before the first queued job is received."""
    try:
        manager = get_model_manager()
        manager.start_autocleanup(
            ttl_seconds=settings.ML_MODEL_IDLE_TTL_SECONDS,
            process_name="worker",
        )
        with SessionLocal() as db:
            runtime = resolve_runtime(load_runtime_preferences(db))
        manager.set_runtime_status(runtime.to_worker_status(source="database"))
    except Exception:  # noqa: BLE001
        # Queue availability is more important than observability during a
        # transient database/Redis startup race. The first job retries this
        # runtime publication through ``_begin_worker_runtime``.
        logger.exception("Failed to initialize worker runtime observability")


class FindWorker(SimpleWorker):
    """SimpleWorker that reports healthy state while waiting for work."""

    def work(self, *args: Any, **kwargs: Any) -> bool:
        initialize_worker_observability()
        return super().work(*args, **kwargs)
