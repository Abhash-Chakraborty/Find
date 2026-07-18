"""
Storage backend factory
Provides a factory function to create and initialize the appropriate storage backend
"""

import logging

from find_api.core.config import settings
from find_api.core.storage_abstract import StorageBackend

logger = logging.getLogger(__name__)


class StorageNotInitializedError(RuntimeError):
    """Raised when process-local storage has not been initialized yet."""


def create_storage_backend() -> StorageBackend:
    """Factory function to create the appropriate storage backend"""
    backend_type = getattr(settings, "STORAGE_BACKEND", "minio").lower()

    if backend_type == "minio":
        from find_api.core.storage_minio import MinIOStorageBackend

        logger.info("Creating MinIO storage backend")
        return MinIOStorageBackend()

    elif backend_type == "local":
        from find_api.core.storage_local import LocalStorageBackend

        logger.info("Creating local filesystem storage backend")
        local_path = getattr(settings, "LOCAL_STORAGE_PATH", "./storage/uploads")
        return LocalStorageBackend(local_path)

    else:
        raise ValueError(
            f"Invalid STORAGE_BACKEND: {backend_type}. Must be 'minio' or 'local'"
        )


async def get_storage() -> StorageBackend:
    """Get and initialize the storage backend"""
    backend = create_storage_backend()
    await backend.init_storage()
    return backend


# Global storage instance
_storage_instance: StorageBackend | None = None


async def initialize_storage() -> None:
    """Initialize the global storage instance at application startup"""
    global _storage_instance
    try:
        _storage_instance = await get_storage()
        logger.info("Storage backend initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize storage backend: {e}")
        raise


def get_storage_instance() -> StorageBackend:
    """Get the global storage instance"""
    if _storage_instance is None:
        raise StorageNotInitializedError(
            "Storage backend not initialized. Call initialize_storage() first."
        )
    return _storage_instance
