"""
MinIO storage backend implementation
Implements StorageBackend interface for MinIO object storage
"""

import asyncio
import json
from datetime import timedelta
from urllib.parse import urlparse, urlunparse
from io import BytesIO
from minio import Minio
from minio.error import S3Error
import logging

from find_api.core.config import settings
from find_api.core.storage_abstract import StorageBackend, StorageException

logger = logging.getLogger(__name__)


class MinIOStorageBackend(StorageBackend):
    """MinIO storage backend implementation"""

    def __init__(self):
        """Initialize MinIO client"""
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self.bucket = settings.MINIO_BUCKET
        self._public_client = self._get_public_client()
        self._public_read_enabled = False

    def _get_public_client(self) -> Minio | None:
        """Get MinIO client for public endpoint if configured"""
        if not settings.MINIO_PUBLIC_ENDPOINT:
            return None

        parsed = urlparse(settings.MINIO_PUBLIC_ENDPOINT.rstrip("/"))
        if not parsed.netloc:
            return None

        return Minio(
            parsed.netloc,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=parsed.scheme == "https",
            region="us-east-1",
        )

    async def init_storage(self) -> None:
        """Initialize MinIO storage - create bucket if not exists"""
        try:
            exists = await asyncio.to_thread(self.client.bucket_exists, self.bucket)
            if not exists:
                if not settings.STORAGE_AUTO_CREATE_BUCKET:
                    raise StorageException(
                        f"Bucket '{self.bucket}' does not exist and "
                        "STORAGE_AUTO_CREATE_BUCKET is disabled"
                    )
                await asyncio.to_thread(self.client.make_bucket, self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
            else:
                logger.info(f"MinIO bucket exists: {self.bucket}")

            if settings.MINIO_PUBLIC_READ:
                await asyncio.to_thread(self._apply_public_read_policy)
            else:
                await asyncio.to_thread(self._remove_public_read_policy)

        except S3Error as e:
            logger.error(f"Failed to initialize MinIO storage: {e}")
            raise StorageException(f"MinIO initialization failed: {e}")

    def _apply_public_read_policy(self) -> None:
        """Apply public read policy to bucket"""
        try:
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
                    }
                ],
            }
            self.client.set_bucket_policy(self.bucket, json.dumps(policy))
            self._public_read_enabled = True
            logger.info(f"Applied public read policy to bucket '{self.bucket}'")
        except S3Error as exc:
            self._public_read_enabled = False
            logger.warning(
                f"Failed to apply public read policy to bucket '{self.bucket}': {exc}. "
                "Falling back to presigned URLs until the policy can be applied."
            )

    def _remove_public_read_policy(self) -> None:
        """Remove public read policy from bucket"""
        try:
            self.client.delete_bucket_policy(self.bucket)
            logger.info(f"Removed public read policy from bucket '{self.bucket}'")
        except S3Error as exc:
            logger.warning(f"Failed to remove public read policy: {exc}")
        finally:
            self._public_read_enabled = False

    async def upload_file(
        self, file_data: bytes, object_name: str, content_type: str = "image/jpeg"
    ) -> str:
        """Upload file to MinIO"""
        try:

            def _upload():
                self.client.put_object(
                    self.bucket,
                    object_name,
                    BytesIO(file_data),
                    length=len(file_data),
                    content_type=content_type,
                )

            await asyncio.to_thread(_upload)
            logger.info(f"Uploaded file to MinIO: {object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Failed to upload file to MinIO: {e}")
            raise StorageException(f"MinIO upload failed: {e}")

    async def get_file(self, object_name: str) -> bytes:
        """Download file from MinIO"""

        def _download():
            response = None
            try:
                response = self.client.get_object(self.bucket, object_name)
                return response.read()
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

        try:
            return await asyncio.to_thread(_download)
        except S3Error as e:
            logger.error(f"Failed to download file from MinIO: {e}")
            raise StorageException(f"MinIO download failed: {e}")

    async def download_file_to_path(
        self, object_name: str, destination_path: str
    ) -> None:
        """Stream file from MinIO to local path"""

        def _stream():
            response = None
            try:
                response = self.client.get_object(self.bucket, object_name)
                with open(destination_path, "wb") as destination:
                    for chunk in response.stream(1024 * 1024):
                        if chunk:
                            destination.write(chunk)
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

        try:
            await asyncio.to_thread(_stream)
        except S3Error as e:
            logger.error(f"Failed to stream file from MinIO: {e}")
            raise StorageException(f"MinIO stream failed: {e}")

    async def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """Get presigned or public URL for file"""
        try:
            if self._public_read_enabled and settings.MINIO_PUBLIC_ENDPOINT:
                parsed = urlparse(settings.MINIO_PUBLIC_ENDPOINT.rstrip("/"))
                object_path = object_name.lstrip("/")
                base_path = parsed.path.rstrip("/")
                if not base_path:
                    public_path = f"/{self.bucket}/{object_path}"
                else:
                    public_path = f"{base_path}/{object_path}"

                return urlunparse(
                    (parsed.scheme, parsed.netloc, public_path, "", "", "")
                )

            signing_client = self._public_client or self.client

            def _presign():
                return signing_client.presigned_get_object(
                    self.bucket, object_name, expires=timedelta(seconds=expires)
                )

            base_url = await asyncio.to_thread(_presign)

            if self._public_client and settings.MINIO_PUBLIC_ENDPOINT:
                parsed = urlparse(settings.MINIO_PUBLIC_ENDPOINT.rstrip("/"))
                base_path = parsed.path.rstrip("/")
                if base_path:
                    signed_parsed = urlparse(base_url)
                    base_url = urlunparse(
                        (
                            signed_parsed.scheme,
                            signed_parsed.netloc,
                            base_path + signed_parsed.path,
                            signed_parsed.params,
                            signed_parsed.query,
                            signed_parsed.fragment,
                        )
                    )
            return base_url
        except S3Error as e:
            logger.error(f"Failed to generate URL: {e}")
            raise StorageException(f"URL generation failed: {e}")

    async def delete_file(self, object_name: str) -> None:
        """Delete file from MinIO"""
        try:
            await asyncio.to_thread(self.client.remove_object, self.bucket, object_name)
            logger.info(f"Deleted file from MinIO: {object_name}")
        except S3Error as e:
            logger.error(f"Failed to delete file from MinIO: {e}")
            raise StorageException(f"MinIO deletion failed: {e}")

    async def file_exists(self, object_name: str) -> bool:
        """Check if file exists in MinIO"""
        try:
            await asyncio.to_thread(self.client.stat_object, self.bucket, object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"Failed to check file existence: {e}")
            raise StorageException(f"File existence check failed: {e}")
