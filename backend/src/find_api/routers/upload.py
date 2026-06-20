"""
Upload endpoint for image ingestion
"""

import hashlib
import io
import logging
import mimetypes
import zipfile
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_optional_user
from find_api.core.queue import get_task_queue
from find_api.core.storage import upload_file, upload_thumbnail
from find_api.models.media import Media
from find_api.models.user import User
from find_api.workers.jobs import analyze_image

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload")
async def upload_images(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Upload one or more images for processing

    Returns:
        List of created media records with job IDs
    """
    results = []

    for file in files:
        try:
            file_data = await file.read()
            result = _ingest_image(
                filename=file.filename,
                content_type=file.content_type,
                file_data=file_data,
                db=db,
                uploader_user_id=user.id if user else None,
            )
            results.append(result)
        except HTTPException:
            raise
        except Exception:
            logger.exception("Failed to upload %s", file.filename)
            results.append(
                {
                    "filename": file.filename,
                    "status": "failed",
                    "error": "Upload failed. Please retry.",
                }
            )

    return {"results": results, "total": len(results)}


@router.post("/upload/bulk")
async def upload_bulk_images(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Upload images in bulk via ZIP archive
    """
    if not file.filename.lower().endswith(".zip") and file.content_type not in {
        "application/zip",
        "application/x-zip-compressed",
        "multipart/x-zip",
    }:
        raise HTTPException(400, "Bulk uploads must be provided as a ZIP archive")

    try:
        archive_bytes = await file.read()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]

            if not members:
                raise HTTPException(400, "ZIP archive is empty")

            # Pre-extraction archive safety checks

            # 1. Reject nested archives
            for info in members:
                name_lower = info.filename.lower()
                if any(
                    name_lower.endswith(ext)
                    for ext in (".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".rar")
                ):
                    raise HTTPException(
                        400,
                        f"ZIP archive contains a nested archive: {info.filename}",
                    )

            # 2. Reject if total uncompressed size exceeds limit
            total_size = sum(info.file_size for info in members)
            max_total = settings.MAX_BULK_TOTAL_SIZE_MB * 1024 * 1024
            if total_size > max_total:
                raise HTTPException(
                    400,
                    f"Total uncompressed size exceeds the limit of {settings.MAX_BULK_TOTAL_SIZE_MB} MB",
                )

            # 3. Reject suspicious compression ratios (ZIP bomb)
            for info in members:
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > settings.MAX_BULK_COMPRESSION_RATIO:
                        raise HTTPException(
                            400,
                            f"File {info.filename} has a suspicious compression ratio of {ratio:.1f}",
                        )

            if len(members) > settings.MAX_BULK_FILES:
                raise HTTPException(
                    400,
                    f"ZIP archive contains more than {settings.MAX_BULK_FILES} files",
                )

            results = []

            max_file_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

            for info in members:
                filename = _get_zip_member_basename(info.filename)

                if not filename:
                    continue

                # Per-file size check
                if info.file_size > max_file_size:
                    results.append(
                        {
                            "filename": filename,
                            "status": "failed",
                            "error": f"File {filename} exceeds max upload size",
                        }
                    )
                    continue

                try:
                    file_data = archive.read(info)
                except KeyError:
                    continue

                if not file_data:
                    results.append(
                        {
                            "filename": filename,
                            "status": "failed",
                            "error": "File is empty",
                        }
                    )
                    continue

                guessed_type = mimetypes.guess_type(filename)[0]

                try:
                    result = _ingest_image(
                        filename=filename,
                        content_type=guessed_type,
                        file_data=file_data,
                        db=db,
                        uploader_user_id=user.id if user else None,
                    )
                    results.append(result)
                except HTTPException as e:
                    detail = e.detail if isinstance(e.detail, str) else str(e.detail)
                    results.append(
                        {
                            "filename": filename,
                            "status": "failed",
                            "error": detail,
                        }
                    )
                except Exception:
                    logger.exception("Failed to process %s from bulk upload", filename)
                    results.append(
                        {
                            "filename": filename,
                            "status": "failed",
                            "error": "Upload failed. Please retry.",
                        }
                    )

    except zipfile.BadZipFile:
        raise HTTPException(400, "Uploaded file is not a valid ZIP archive")

    return {"results": results, "total": len(results)}


def _get_zip_member_basename(member_name: str) -> str:
    """Return only the final filename from a ZIP member path."""
    return member_name.replace("\\", "/").split("/")[-1]


def _ingest_image(
    *,
    filename: str,
    content_type: Optional[str],
    file_data: bytes,
    db: Session,
    uploader_user_id: Optional[int] = None,
) -> dict:
    """Create or reuse a media record from raw image bytes"""
    detected_type = content_type or mimetypes.guess_type(filename)[0] or ""

    if not detected_type.startswith("image/"):
        raise HTTPException(400, f"File {filename} is not an image")

    # Verify image content and protect against decompression bombs
    try:
        # Set a reasonable limit for image pixels (e.g., 100MP)
        Image.MAX_IMAGE_PIXELS = 100_000_000
        with Image.open(io.BytesIO(file_data)) as img:
            img.verify()
            # Re-open to check dimensions (verify() consumes the file pointer)
            # This is still lazy and doesn't decode pixels.
            with Image.open(io.BytesIO(file_data)) as img2:
                _ = img2.size
    except Exception:
        raise HTTPException(400, f"File {filename} is corrupted or not a valid image")

    file_size = len(file_data)
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if file_size > max_size:
        raise HTTPException(400, f"File {filename} exceeds max size")

    file_hash = hashlib.sha256(file_data).hexdigest()

    existing = db.query(Media).filter(Media.file_hash == file_hash).first()
    if existing:
        if uploader_user_id is not None and existing.uploader_user_id is None:
            existing.uploader_user_id = uploader_user_id
            db.commit()
        logger.info(f"File {filename} already exists (hash: {file_hash})")
        return {"filename": filename, "status": "duplicate", "media_id": existing.id}

    minio_key = (
        f"images/{file_hash[:2]}/{file_hash}{_get_extension(filename, detected_type)}"
    )

    upload_file(file_data, minio_key, detected_type)
    thumbnail_metadata = upload_thumbnail(file_data, file_hash)

    media_kwargs = {
        "file_hash": file_hash,
        "minio_key": minio_key,
        "filename": filename,
        "content_type": detected_type,
        "file_size": file_size,
        "status": "pending",
        **(thumbnail_metadata or {}),
    }
    if uploader_user_id is not None:
        media_kwargs["uploader_user_id"] = uploader_user_id

    media = Media(**media_kwargs)

    db.add(media)
    db.commit()
    db.refresh(media)

    job = get_task_queue().enqueue(
        analyze_image, media.id, job_timeout=settings.WORKER_TIMEOUT
    )
    media.analysis_job_id = job.id
    db.commit()

    logger.info(f"Uploaded {filename} (media_id: {media.id}, job_id: {job.id})")

    return {
        "filename": filename,
        "status": "uploaded",
        "media_id": media.id,
        "job_id": job.id,
    }


def _get_extension(filename: str, content_type: Optional[str]) -> str:
    """Determine appropriate file extension for storage"""
    if "." in filename:
        return "." + filename.split(".")[-1]

    if content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            if guessed == ".jpe":
                return ".jpg"
            return guessed

    return ""
