"""
Storage module - provides unified interface for file storage operations
Uses factory pattern to support multiple storage backends
"""

import logging

from find_api.core.storage_factory import get_storage_instance
from find_api.core.storage_minio import upload_thumbnail

logger = logging.getLogger(__name__)


async def init_storage():
    """Initialize storage backend during application startup"""
    try:
        from find_api.core.storage_factory import initialize_storage

        await initialize_storage()
        logger.info("Storage backend initialized")
    except Exception as e:
        logger.error(f"Failed to initialize storage: {e}")
        raise


async def upload_file(
    file_data: bytes, object_name: str, content_type: str = "image/jpeg"
) -> str:
    """Upload file to storage backend"""
    backend = get_storage_instance()
    return await backend.upload_file(file_data, object_name, content_type)


async def get_file(object_name: str) -> bytes:
    """Download file from storage backend"""
    backend = get_storage_instance()
    return await backend.get_file(object_name)


async def download_file_to_path(object_name: str, destination_path: str) -> None:
    """Stream a storage object to a local path without loading into memory"""
    backend = get_storage_instance()
    await backend.download_file_to_path(object_name, destination_path)


async def get_file_url(object_name: str, expires: int = 3600) -> str:
    """Get presigned URL for file"""
    backend = get_storage_instance()
    return await backend.get_file_url(object_name, expires)


async def delete_file(object_name: str) -> None:
    """Delete file from storage backend"""
    backend = get_storage_instance()
    await backend.delete_file(object_name)


async def file_exists(object_name: str) -> bool:
    """Check if file exists in storage backend"""
    backend = get_storage_instance()
    return await backend.file_exists(object_name)


async def upload_file_with_thumbnail(
    file_data: bytes, object_name: str, file_hash: str, content_type: str = "image/jpeg"
) -> tuple[str, dict | None]:
    """Upload file and generate thumbnail"""
    backend = get_storage_instance()
    result = await backend.upload_file(file_data, object_name, content_type)
    thumbnail_meta = await upload_thumbnail(backend, file_data, file_hash)
    return result, thumbnail_meta
