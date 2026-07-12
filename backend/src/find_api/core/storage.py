"""Provider-neutral storage facade used by routes and workers.

The app-level helpers intentionally remain synchronous because existing FastAPI
routes and RQ workers call this module directly. Individual backend
implementations can still use async internals to move blocking SDK/filesystem
work off their event loop.
"""

import asyncio
import logging
import threading

from find_api.core.storage_factory import (
    StorageNotInitializedError,
    get_storage_instance,
)
from find_api.core.storage_thumbnails import (
    THUMBNAIL_CONTENT_TYPE,
    generate_thumbnail,
    upload_thumbnail as upload_thumbnail_to_backend,
)

logger = logging.getLogger(__name__)
_storage_init_lock = threading.Lock()

__all__ = [
    "THUMBNAIL_CONTENT_TYPE",
    "delete_file",
    "download_file_to_path",
    "file_exists",
    "generate_thumbnail",
    "get_file",
    "get_file_url",
    "init_storage",
    "upload_file",
    "upload_file_with_thumbnail",
    "upload_thumbnail",
]


def _run_backend_call(coro):
    """Run an async backend method from sync routes, workers, or app startup."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, object] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    return result.get("value")


def init_storage():
    """Initialize storage backend during application startup"""
    try:
        from find_api.core.storage_factory import initialize_storage

        _run_backend_call(initialize_storage())
        logger.info("Storage backend initialized")
    except Exception as e:
        logger.error(f"Failed to initialize storage: {e}")
        raise


def _get_or_init_storage():
    """Return the process-local backend, initializing it for worker processes.

    FastAPI initializes storage during lifespan startup, but RQ workers are
    separate processes and never execute that lifespan. Lazy initialization
    keeps the route behavior unchanged while ensuring the first worker storage
    operation creates its own process-local backend exactly once.
    """
    try:
        return get_storage_instance()
    except StorageNotInitializedError:
        pass

    with _storage_init_lock:
        try:
            return get_storage_instance()
        except StorageNotInitializedError:
            init_storage()
            return get_storage_instance()


def upload_file(
    file_data: bytes, object_name: str, content_type: str = "image/jpeg"
) -> str:
    """Upload file to storage backend"""
    backend = _get_or_init_storage()
    return _run_backend_call(backend.upload_file(file_data, object_name, content_type))


def get_file(object_name: str) -> bytes:
    """Download file from storage backend"""
    backend = _get_or_init_storage()
    return _run_backend_call(backend.get_file(object_name))


def download_file_to_path(object_name: str, destination_path: str) -> None:
    """Stream a storage object to a local path without loading into memory"""
    backend = _get_or_init_storage()
    _run_backend_call(backend.download_file_to_path(object_name, destination_path))


def get_file_url(object_name: str, expires: int = 3600) -> str:
    """Get presigned URL for file"""
    backend = _get_or_init_storage()
    return _run_backend_call(backend.get_file_url(object_name, expires))


def delete_file(object_name: str) -> None:
    """Delete file from storage backend"""
    backend = _get_or_init_storage()
    _run_backend_call(backend.delete_file(object_name))


def file_exists(object_name: str) -> bool:
    """Check if file exists in storage backend"""
    backend = _get_or_init_storage()
    return _run_backend_call(backend.file_exists(object_name))


def upload_thumbnail(file_data: bytes, file_hash: str) -> dict | None:
    """Generate and upload a thumbnail with the configured storage backend."""
    backend = _get_or_init_storage()
    return _run_backend_call(upload_thumbnail_to_backend(backend, file_data, file_hash))


def upload_file_with_thumbnail(
    file_data: bytes, object_name: str, file_hash: str, content_type: str = "image/jpeg"
) -> tuple[str, dict | None]:
    """Upload file and generate thumbnail"""
    backend = _get_or_init_storage()
    result = _run_backend_call(
        backend.upload_file(file_data, object_name, content_type)
    )
    thumbnail_meta = _run_backend_call(
        upload_thumbnail_to_backend(backend, file_data, file_hash)
    )
    return result, thumbnail_meta
