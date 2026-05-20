"""
Model Manager for efficient GPU resource management
"""

import asyncio
import gc
import logging
import threading
import time
from typing import Any, Callable, Dict, List

from find_api.core.config import settings

try:
    import torch
except ImportError:
    torch = None

logger = logging.getLogger(__name__)


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
        self.last_used: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.gpu_lock = asyncio.Lock()
        self._cleanup_thread = None
        self._initialized = True
        self.max_loaded_models = settings.ML_MAX_LOADED_MODELS
        logger.info(
            f"ModelManager initialized (max_models={self.max_loaded_models}) with GPU Lock and Lazy Loading support"
        )

    def set_max_models(self, count: int):
        """Set maximum number of concurrent models to keep in memory"""
        with self._lock:
            self.max_loaded_models = count

    def start_autocleanup(self, interval_seconds: int = 60, ttl_seconds: int = 300):
        """Start background thread for automatic idle unloading"""
        with self._lock:
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

    def get_model(self, name: str, loader: Callable[[], Any]) -> Any:
        """
        Get a model instance, loading it if necessary.

        Args:
            name: Unique identifier for the model
            loader: Function that returns the loaded model

        Returns:
            The model instance
        """
        with self._lock:
            if name not in self.models:
                # Check if we need to unload something to make room
                if len(self.models) >= self.max_loaded_models:
                    # Unload oldest (least recently used)
                    # We sort by last_used time
                    sorted_models = sorted(self.last_used.items(), key=lambda x: x[1])
                    for oldest_name, _ in sorted_models:
                        if oldest_name in self.models and oldest_name != name:
                            logger.info(
                                f"Max models reached ({self.max_loaded_models}). Unloading oldest: {oldest_name}"
                            )
                            del self.models[oldest_name]
                            del self.last_used[oldest_name]
                            # Only need to unload one to make room
                            break

                logger.info(f"Lazy-loading model: {name}")
                try:
                    self.models[name] = loader()
                    logger.info(f"Model loaded successfully: {name}")
                except Exception:
                    logger.exception("Failed to load model %s", name)
                    raise

            self.last_used[name] = time.time()
            return self.models[name]

    def unload_idle_models(self, ttl_seconds: int):
        """
        Unload models that haven't been used for ttl_seconds.
        """
        now = time.time()
        to_unload = []

        with self._lock:
            for name, last_ts in self.last_used.items():
                if name in self.models and (now - last_ts) > ttl_seconds:
                    to_unload.append(name)

            if not to_unload:
                return

            for name in to_unload:
                logger.info(
                    f"Unloading idle model: {name} (idle for {now - self.last_used[name]:.1f}s)"
                )
                del self.models[name]
                del self.last_used[name]

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


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get global ModelManager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
