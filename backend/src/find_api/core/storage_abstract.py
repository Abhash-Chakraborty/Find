"""
Abstract storage backend interface - provider-neutral
Defines the contract that all storage backends must implement
"""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """
    Abstract base class for storage backends.

    All storage backends (MinIO, local filesystem, S3, etc.) must implement
    this interface to ensure consistent behavior across different storage providers.
    """

    @abstractmethod
    async def init_storage(self) -> None:
        """Initialize storage backend."""
        pass

    @abstractmethod
    async def upload_file(
        self, file_data: bytes, object_name: str, content_type: str = "image/jpeg"
    ) -> str:
        """Upload file to storage."""
        pass

    @abstractmethod
    async def get_file(self, object_name: str) -> bytes:
        """Download file from storage."""
        pass

    @abstractmethod
    async def download_file_to_path(
        self, object_name: str, destination_path: str
    ) -> None:
        """Stream file from storage to local filesystem."""
        pass

    @abstractmethod
    async def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """Get public/accessible URL for file."""
        pass

    @abstractmethod
    async def delete_file(self, object_name: str) -> None:
        """Delete file from storage."""
        pass

    @abstractmethod
    async def file_exists(self, object_name: str) -> bool:
        """Check if file exists in storage."""
        pass


class StorageException(Exception):
    """Base exception for storage operations"""

    pass
