"""
Model Manager for efficient GPU resource management
"""

import asyncio
import gc
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List

from find_api.core.config import settings

try:
    import torch
except ImportError:
    torch = None

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
    Also supports lazy-loading and idle unloading to save memory.
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
        self.in_flight: Dict[str, int] = {}
        self.last_used: Dict[str, float] = {}
        self._loading: Dict[str, threading.Event] = {}
        self.failed_loads: Dict[str, Dict[str, Any]] = {}
        self.unavailable_models: Dict[str, ModelLoadFailure] = {}
        self._lock = threading.RLock()
        self.gpu_lock = asyncio.Lock()
        self._cleanup_thread = None
        self.process_name = os.getenv("MODEL_MANAGER_PROCESS_NAME", "api")
        self._initialized = True
        self.max_loaded_models = settings.ML_MAX_LOADED_MODELS
        logger.info(
            f"ModelManager initialized (max_models={self.max_loaded_models}) with GPU Lock and Lazy Loading support"
        )

    def set_max_models(self, count: int):
        """Set maximum number of concurrent models to keep in memory"""
        with self._lock:
            if not isinstance(count, int) or count <= 0:
                raise ValueError("max loaded models must be a positive integer")
            self.max_loaded_models = count

    def start_autocleanup(
        self,
        interval_seconds: int = 60,
        ttl_seconds: int = 300,
        process_name: str | None = None,
    ):
        """Start background thread for automatic idle unloading"""
        with self._lock:
            if process_name:
                self.process_name = process_name
            self.publish_status()

            if self._cleanup_thread and self._cleanup_thread.is_alive():
                return

            def cleanup_loop():
                logger.info(
                    f"Background ML model cleanup started (interval={interval_seconds}s, ttl={ttl_seconds}s)"
                )
                while True:
                    try:
                        time.sleep(interval_seconds)
                        self.unload_idle_models(ttl_seconds)
                    except Exception as e:
                        logger.error(f"Error in model cleanup thread: {e}")

            self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
            self._cleanup_thread.start()

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
        while True:
            with self._lock:
                if name in self.models:
                    self.last_used[name] = time.time()
                    return self.models[name]

                if name in self.unavailable_models:
                    failure = self.unavailable_models[name]
                    if failure.config_key != config_key:
                        logger.info(
                            "Retrying unavailable model %s because configuration changed",
                            name,
                        )
                        self._clear_model_failure_locked(name)
                    else:
                        logger.warning(
                            "Skipping load for unavailable model %s: %s",
                            name,
                            failure.reason,
                        )
                        raise ModelUnavailableError(name, failure)

                loading_event = self._loading.get(name)
                if loading_event is None:
                    loading_event = threading.Event()
                    self._loading[name] = loading_event
                    break

            loading_event.wait()

        logger.info("Lazy-loading model: %s", name)
        try:
            model = loader()
        except Exception as exc:
            failed_at = datetime.now(timezone.utc)
            failure = ModelLoadFailure(
                name=name,
                error_type=exc.__class__.__name__,
                reason=_safe_failure_reason(exc),
                failed_at=failed_at,
                config_key=config_key,
            )
            with self._lock:
                self.unavailable_models[name] = failure
                self.failed_loads[name] = {
                    "error": failure.reason,
                    "error_type": failure.error_type,
                    "failed_at": time.time(),
                    "config_key": config_key,
                }
                self._loading.pop(name, None)
                loading_event.set()
                self.publish_status()
            logger.exception("Failed to load model %s", name)
            raise ModelUnavailableError(name, failure) from exc

        with self._lock:
            try:
                if name in self.models:
                    return self.models[name]

                self._evict_for_capacity_locked(skip={name})
                self.models[name] = model
                self.in_flight.setdefault(name, 0)
                self.last_used[name] = time.time()
                self.failed_loads.pop(name, None)
                self.unavailable_models.pop(name, None)
                self.publish_status()
                logger.info("Model loaded successfully: %s", name)
                return model
            finally:
                self._loading.pop(name, None)
                loading_event.set()

    @contextmanager
    def use_model(
        self, name: str, loader: Callable[[], Any], config_key: str | None = None
    ) -> Iterator[Any]:
        """Lease a model for inference so idle cleanup cannot unload it mid-use."""
        model = self.get_model(name, loader, config_key=config_key)
        with self._lock:
            self.in_flight[name] = self.in_flight.get(name, 0) + 1
        try:
            yield model
        finally:
            self.release_model(name)

    def release_model(self, name: str):
        """Release a model lease and update its idle timestamp."""
        with self._lock:
            count = self.in_flight.get(name, 0)
            if count <= 1:
                self.in_flight[name] = 0
            else:
                self.in_flight[name] = count - 1
            if name in self.models:
                self.last_used[name] = time.time()
            self.publish_status()

    def unload_idle_models(self, ttl_seconds: int):
        """
        Unload models that haven't been used for ttl_seconds.
        """
        now = time.time()
        to_unload = []

        with self._lock:
            for name, last_ts in self.last_used.items():
                if (
                    name in self.models
                    and self.in_flight.get(name, 0) == 0
                    and (now - last_ts) > ttl_seconds
                ):
                    to_unload.append(name)

            if not to_unload:
                return

            for name in to_unload:
                logger.info(
                    f"Unloading idle model: {name} (idle for {now - self.last_used[name]:.1f}s)"
                )
                self._drop_model_locked(name)
            self.publish_status()

        # Force garbage collection outside the lock to avoid blocking other threads
        gc.collect()

        # Clear CUDA cache if possible
        if torch is not None and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                logger.debug("CUDA cache cleared after model unloading")
            except Exception as e:
                logger.warning(f"Failed to clear CUDA cache: {e}")

    def get_loaded_models(self) -> List[str]:
        """Get list of currently loaded model names"""
        with self._lock:
            return list(self.models.keys())

    def reset_for_tests(self):
        """Reset mutable singleton state for focused tests."""
        with self._lock:
            self.models.clear()
            self.in_flight.clear()
            self.last_used.clear()
            self._loading.clear()
            self.failed_loads.clear()
            self.unavailable_models.clear()
            self.max_loaded_models = settings.ML_MAX_LOADED_MODELS
            self.publish_status()

    def get_status(self) -> Dict[str, Any]:
        """Return current process model-manager status."""
        with self._lock:
            return {
                "process": self.process_name,
                "loaded_models": list(self.models.keys()),
                "in_flight": {
                    name: count for name, count in self.in_flight.items() if count > 0
                },
                "failed_models": self.failed_loads.copy(),
                "max_loaded_models": self.max_loaded_models,
                "updated_at": time.time(),
            }

    def publish_status(self):
        """Best-effort publish of this process model state for API observability."""
        try:
            from redis import Redis

            redis_conn = Redis.from_url(settings.REDIS_URL)
            key = f"find:model_status:{self.process_name}"
            redis_conn.setex(key, 600, json.dumps(self.get_status()))
        except Exception as exc:
            logger.debug("Failed to publish model manager status: %s", exc)

    def _drop_model_locked(self, name: str):
        self.models.pop(name, None)
        self.last_used.pop(name, None)
        self.in_flight.pop(name, None)

    def _evict_for_capacity_locked(self, skip: set[str] | None = None):
        skip = skip or set()
        while len(self.models) >= self.max_loaded_models:
            candidates = [
                (model_name, last_ts)
                for model_name, last_ts in self.last_used.items()
                if model_name not in skip
                and model_name in self.models
                and self.in_flight.get(model_name, 0) == 0
            ]
            if not candidates:
                logger.warning(
                    "Model capacity reached but all loaded models are in use; temporarily allowing %s loaded models",
                    len(self.models) + 1,
                )
                return

            oldest_name, _ = min(candidates, key=lambda item: item[1])
            logger.info(
                "Max models reached (%s). Unloading least recently used model: %s",
                self.max_loaded_models,
                oldest_name,
            )
            self._drop_model_locked(oldest_name)

    def _clear_model_failure_locked(self, name: str) -> None:
        self.unavailable_models.pop(name, None)
        self.failed_loads.pop(name, None)

    def clear_model_failure(self, name: str) -> None:
        """Allow a known-unavailable model to be retried."""
        with self._lock:
            self._clear_model_failure_locked(name)
            self.publish_status()

    def clear_model_failures(self, names: list[str] | tuple[str, ...]) -> None:
        """Allow multiple known-unavailable models to be retried."""
        with self._lock:
            for name in names:
                self._clear_model_failure_locked(name)
            self.publish_status()

    def clear(self) -> None:
        """Clear cached models and failures for tests or controlled reloads."""
        self.reset_for_tests()


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get global ModelManager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
