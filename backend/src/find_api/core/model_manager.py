"""
Model Manager for efficient GPU resource management
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelLoadFailure:
    """Safe process-local record for a failed model load."""

    name: str
    error_type: str
    reason: str
    failed_at: datetime
    config_key: str | None = None


class ModelUnavailableError(RuntimeError):
    """Raised when a model is known to be unavailable in this process."""

    def __init__(self, name: str, failure: ModelLoadFailure):
        self.name = name
        self.failure = failure
        super().__init__(
            f"Model '{name}' is unavailable after a failed load. "
            "Restart the worker or clear model failure state to retry."
        )


def _safe_failure_reason(exc: Exception) -> str:
    """Return a short single-line reason for logs and diagnostics."""
    message = str(exc).replace("\n", " ").strip()
    if not message:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {message[:240]}"


class ModelManager:
    """
    Singleton class to manage ML models and GPU resources.
    Ensures that heavy GPU tasks are serialized to prevent OOM on 4GB VRAM.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.models: Dict[str, Any] = {}
        self.unavailable_models: Dict[str, ModelLoadFailure] = {}
        self.gpu_lock = asyncio.Lock()
        self._initialized = True
        logger.info("ModelManager initialized with GPU Lock")

    async def acquire_lock(self):
        """Acquire GPU lock"""
        if not self.gpu_lock.locked():
            logger.debug("Acquiring GPU lock...")
        await self.gpu_lock.acquire()
        logger.debug("GPU lock acquired")

    def release_lock(self):
        """Release GPU lock"""
        if self.gpu_lock.locked():
            self.gpu_lock.release()
            logger.debug("GPU lock released")

    def get_model(
        self, name: str, loader: Callable[[], Any], config_key: str | None = None
    ) -> Any:
        """
        Get a model instance, loading it if necessary.

        Args:
            name: Unique identifier for the model
            loader: Function that returns the loaded model
            config_key: Optional model configuration fingerprint. When it changes,
                a previously unavailable model is allowed to retry.

        Returns:
            The model instance
        """
        if name in self.unavailable_models:
            failure = self.unavailable_models[name]
            if failure.config_key is not None and failure.config_key != config_key:
                logger.info(
                    "Retrying unavailable model %s because configuration changed",
                    name,
                )
                self.clear_model_failure(name)
            else:
                logger.warning(
                    "Skipping load for unavailable model %s: %s",
                    name,
                    failure.reason,
                )
                raise ModelUnavailableError(name, failure)

        if name not in self.models:
            logger.info(f"Loading model: {name}")
            try:
                self.models[name] = loader()
                logger.info(f"Model loaded successfully: {name}")
            except Exception as exc:
                failure = ModelLoadFailure(
                    name=name,
                    error_type=exc.__class__.__name__,
                    reason=_safe_failure_reason(exc),
                    failed_at=datetime.now(timezone.utc),
                    config_key=config_key,
                )
                self.unavailable_models[name] = failure
                logger.exception("Failed to load model %s", name)
                raise ModelUnavailableError(name, failure) from exc

        return self.models[name]

    def clear_model_failure(self, name: str) -> None:
        """Allow a known-unavailable model to be retried."""
        self.unavailable_models.pop(name, None)

    def clear(self) -> None:
        """Clear cached models and failures for tests or controlled reloads."""
        self.models.clear()
        self.unavailable_models.clear()


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get global ModelManager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
