"""
MinIO storage configuration and utilities
"""
import json
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.core.config import settings
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# Create MinIO client
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE
)


def init_storage():
    """
    Initialize MinIO storage - create bucket if not exists
    """
    try:
        # Check if bucket exists
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
            logger.info(f"Created MinIO bucket: {settings.MINIO_BUCKET}")
        else:
            logger.info(f"MinIO bucket exists: {settings.MINIO_BUCKET}")
        if settings.MINIO_PUBLIC_READ:
            try:
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": ["*"]},
                            "Action": ["s3:GetObject"],
                            "Resource": [
                                f"arn:aws:s3:::{settings.MINIO_BUCKET}/*"
                            ],
                        }
                    ],
                }
                minio_client.set_bucket_policy(
                    settings.MINIO_BUCKET,
                    json.dumps(policy),
                )
                logger.info(
                    "Applied public read policy to MinIO bucket '%s'",
                    settings.MINIO_BUCKET,
                )
            except S3Error as exc:
                logger.warning(
                    "Failed to apply public read policy: %s", exc
                )
    except S3Error as e:
        logger.error(f"Failed to initialize MinIO storage: {e}")
        raise


def upload_file(file_data: bytes, object_name: str, content_type: str = "image/jpeg") -> str:
    """
    Upload file to MinIO
    
    Args:
        file_data: File bytes
        object_name: Object name in bucket
        content_type: MIME type
        
    Returns:
        Object name in bucket
    """
    try:
        minio_client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            BytesIO(file_data),
            length=len(file_data),
            content_type=content_type
        )
        logger.info(f"Uploaded file to MinIO: {object_name}")
        return object_name
    except S3Error as e:
        logger.error(f"Failed to upload file to MinIO: {e}")
        raise


def get_file(object_name: str) -> bytes:
    """
    Download file from MinIO
    
    Args:
        object_name: Object name in bucket
        
    Returns:
        File bytes
    """
    try:
        response = minio_client.get_object(settings.MINIO_BUCKET, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        logger.error(f"Failed to download file from MinIO: {e}")
        raise


def get_file_url(object_name: str, expires: int = 3600) -> str:
    """
    Get presigned URL for file
    
    Args:
        object_name: Object name in bucket
        expires: URL expiry in seconds
        
    Returns:
        Presigned URL
    """
    try:
        if settings.MINIO_PUBLIC_READ and settings.MINIO_PUBLIC_ENDPOINT:
            base = settings.MINIO_PUBLIC_ENDPOINT.rstrip("/")
            path = object_name.lstrip("/")
            return f"{base}/{path}"

        return minio_client.presigned_get_object(
            settings.MINIO_BUCKET,
            object_name,
            expires=timedelta(seconds=expires)
        )
    except S3Error as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise


def delete_file(object_name: str):
    """
    Delete file from MinIO
    
    Args:
        object_name: Object name in bucket
    """
    try:
        minio_client.remove_object(settings.MINIO_BUCKET, object_name)
        logger.info(f"Deleted file from MinIO: {object_name}")
    except S3Error as e:
        logger.error(f"Failed to delete file from MinIO: {e}")
        raise
