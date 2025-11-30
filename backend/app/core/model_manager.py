"""
Model Manager for efficient GPU resource management
"""

import asyncio
import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


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

    def get_model(self, name: str, loader: Callable[[], Any]) -> Any:
        """
        Get a model instance, loading it if necessary.

        Args:
            name: Unique identifier for the model
            loader: Function that returns the loaded model

        Returns:
            The model instance
        """
        if name not in self.models:
            logger.info(f"Loading model: {name}")
            try:
                self.models[name] = loader()
                logger.info(f"Model loaded successfully: {name}")
            except Exception as e:
                logger.error(f"Failed to load model {name}: {e}")
                raise

        return self.models[name]


# Global instance
_model_manager = None


def get_model_manager() -> ModelManager:
    """Get global ModelManager instance"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
