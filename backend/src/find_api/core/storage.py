"""
MinIO storage configuration and utilities
"""

import json
from datetime import timedelta
from urllib.parse import urlparse, urlunparse
from minio import Minio
from minio.error import S3Error
from find_api.core.config import settings
import logging
from io import BytesIO
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = (256, 256)
THUMBNAIL_CONTENT_TYPE = "image/webp"
THUMBNAIL_EXTENSION = ".webp"
THUMBNAIL_QUALITY = 78

# Create MinIO client
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


def _get_public_minio_client() -> Minio | None:
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
                            "Resource": [f"arn:aws:s3:::{settings.MINIO_BUCKET}/*"],
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
                logger.warning("Failed to apply public read policy: %s", exc)
        else:
            try:
                minio_client.delete_bucket_policy(settings.MINIO_BUCKET)
                logger.info(
                    "Removed public read policy from MinIO bucket '%s'",
                    settings.MINIO_BUCKET,
                )
            except S3Error as exc:
                logger.warning("Failed to remove public read policy: %s", exc)
    except S3Error as e:
        logger.error(f"Failed to initialize MinIO storage: {e}")
        raise


def upload_file(
    file_data: bytes, object_name: str, content_type: str = "image/jpeg"
) -> str:
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
            content_type=content_type,
        )
        logger.info(f"Uploaded file to MinIO: {object_name}")
        return object_name
    except S3Error as e:
        logger.error(f"Failed to upload file to MinIO: {e}")
        raise


def generate_thumbnail(file_data: bytes) -> tuple[bytes, int, int]:
    """
    Generate a small WEBP thumbnail from image bytes.

    The original bytes are never modified. Any caller should treat failures as
    non-fatal so image ingestion and analysis can continue without thumbnails.
    """
    with Image.open(BytesIO(file_data)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(
            output,
            format="WEBP",
            quality=THUMBNAIL_QUALITY,
            method=4,
        )
        thumbnail_data = output.getvalue()

    return thumbnail_data, image.width, image.height


def upload_thumbnail(file_data: bytes, file_hash: str) -> dict | None:
    """
    Generate and upload a thumbnail for an image.

    Returns thumbnail storage metadata, or None when thumbnail creation/upload
    fails. Original image storage must not depend on this helper succeeding.
    """
    thumbnail_key = f"thumbnails/{file_hash[:2]}/{file_hash}{THUMBNAIL_EXTENSION}"

    try:
        thumbnail_data, width, height = generate_thumbnail(file_data)
        upload_file(thumbnail_data, thumbnail_key, THUMBNAIL_CONTENT_TYPE)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to generate thumbnail for image hash %s: %s",
            file_hash,
            exc,
        )
        return None

    return {
        "thumbnail_key": thumbnail_key,
        "thumbnail_content_type": THUMBNAIL_CONTENT_TYPE,
        "thumbnail_size": len(thumbnail_data),
        "thumbnail_width": width,
        "thumbnail_height": height,
    }


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


def download_file_to_path(object_name: str, destination_path: str) -> None:
    """
    Stream a MinIO object to a local path without loading it all into memory.

    Args:
        object_name: Object name in bucket
        destination_path: Local filesystem path to write
    """
    response = None
    try:
        response = minio_client.get_object(settings.MINIO_BUCKET, object_name)
        with open(destination_path, "wb") as destination:
            for chunk in response.stream(1024 * 1024):
                if chunk:
                    destination.write(chunk)
    except S3Error as e:
        logger.error(f"Failed to stream file from MinIO: {e}")
        raise
    finally:
        if response is not None:
            response.close()
            response.release_conn()


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
            parsed = urlparse(settings.MINIO_PUBLIC_ENDPOINT.rstrip("/"))
            object_path = object_name.lstrip("/")

            base_path = parsed.path.rstrip("/")
            if not base_path:
                public_path = f"/{settings.MINIO_BUCKET}/{object_path}"
            else:
                public_path = f"{base_path}/{object_path}"

            return urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    public_path,
                    "",
                    "",
                    "",
                )
            )

        signing_client = _get_public_minio_client() or minio_client
        return signing_client.presigned_get_object(
            settings.MINIO_BUCKET, object_name, expires=timedelta(seconds=expires)
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
