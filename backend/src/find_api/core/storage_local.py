"""
Local filesystem storage backend implementation
Implements StorageBackend interface for local file storage (desktop mode)
"""

import asyncio
import logging
from pathlib import Path

from find_api.core.storage_abstract import StorageBackend, StorageException

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend"""

    def __init__(self, base_path: str):
        """Initialize local storage backend"""
        self.base_path = Path(base_path).resolve()

    async def init_storage(self) -> None:
        """Initialize storage by creating base directory"""
        try:
            await asyncio.to_thread(self.base_path.mkdir, parents=True, exist_ok=True)
            logger.info(f"Initialized local storage at: {self.base_path}")
        except Exception as e:
            logger.error(f"Failed to initialize local storage: {e}")
            raise StorageException(f"Failed to create storage directory: {e}")

    def _validate_path(self, object_name: str) -> Path:
        """Validate and normalize object path to prevent path traversal"""
        object_name = object_name.lstrip("/").lstrip("\\")

        if ".." in object_name:
            raise StorageException(f"Path traversal detected: {object_name}")

        full_path = (self.base_path / object_name).resolve()

        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise StorageException(f"Path is outside storage directory: {object_name}")

        return full_path

    async def upload_file(
        self, file_data: bytes, object_name: str, content_type: str = "image/jpeg"
    ) -> str:
        """Upload file to local filesystem"""
        try:
            full_path = self._validate_path(object_name)

            def _write():
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(file_data)

            await asyncio.to_thread(_write)

            logger.info(f"Uploaded file to local storage: {object_name}")
            return object_name

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to upload file: {e}")
            raise StorageException(f"Upload failed: {e}")

    async def get_file(self, object_name: str) -> bytes:
        """Download file from local filesystem"""
        try:
            full_path = self._validate_path(object_name)

            def _read():
                if not full_path.is_file():
                    raise StorageException(f"File not found: {object_name}")
                with open(full_path, "rb") as f:
                    return f.read()

            data = await asyncio.to_thread(_read)

            logger.info(f"Downloaded file from local storage: {object_name}")
            return data

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to download file: {e}")
            raise StorageException(f"Download failed: {e}")

    async def download_file_to_path(
        self, object_name: str, destination_path: str
    ) -> None:
        """Stream file from local filesystem to destination path"""
        try:
            full_path = self._validate_path(object_name)

            def _copy():
                if not full_path.is_file():
                    raise StorageException(f"File not found: {object_name}")
                dest = Path(destination_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, "rb") as src:
                    with open(destination_path, "wb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            dst.write(chunk)

            await asyncio.to_thread(_copy)

            logger.info(f"Streamed file from local storage: {object_name}")

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to stream file: {e}")
            raise StorageException(f"Stream failed: {e}")

    async def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """Get local file path as URL"""
        try:
            full_path = self._validate_path(object_name)

            exists = await asyncio.to_thread(full_path.is_file)
            if not exists:
                raise StorageException(f"File not found: {object_name}")

            relative_path = full_path.relative_to(self.base_path)
            return f"/files/{relative_path.as_posix()}"

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate URL: {e}")
            raise StorageException(f"URL generation failed: {e}")

    async def delete_file(self, object_name: str) -> None:
        """Delete file from local filesystem"""
        try:
            full_path = self._validate_path(object_name)

            def _delete():
                if full_path.is_file():
                    full_path.unlink()
                    return True
                return False

            deleted = await asyncio.to_thread(_delete)

            if deleted:
                logger.info(f"Deleted file from local storage: {object_name}")
            else:
                logger.warning(f"File not found for deletion: {object_name}")

        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            raise StorageException(f"Deletion failed: {e}")

    async def file_exists(self, object_name: str) -> bool:
        """Check if file exists in local filesystem"""
        try:
            full_path = self._validate_path(object_name)
            return await asyncio.to_thread(full_path.is_file)
        except StorageException:
            raise
        except Exception as e:
            logger.error(f"Failed to check file existence: {e}")
            raise StorageException(f"Existence check failed: {e}")
