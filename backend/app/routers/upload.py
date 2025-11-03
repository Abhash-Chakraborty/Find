"""
Upload endpoint for image ingestion
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
import hashlib
import io
import logging
import mimetypes
import zipfile
from redis import Redis
from rq import Queue  # type: ignore[import-untyped]

from app.core.database import get_db
from app.core.storage import upload_file
from app.core.config import settings
from app.models.media import Media
from app.workers.jobs import analyze_image

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize Redis queue
redis_conn = Redis.from_url(settings.REDIS_URL)
task_queue = Queue(connection=redis_conn)


@router.post("/upload")
async def upload_images(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
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
            )
            results.append(result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to upload {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "status": "failed",
                "error": str(e)
            })
    
    return {"results": results, "total": len(results)}


@router.post("/upload/bulk")
async def upload_bulk_images(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
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

            if len(members) > settings.MAX_BULK_FILES:
                raise HTTPException(
                    400,
                    f"ZIP archive contains more than {settings.MAX_BULK_FILES} files",
                )

            results = []

            for info in members:
                filename = info.filename.split("/")[-1]

                if not filename:
                    continue

                try:
                    file_data = archive.read(info)
                except KeyError:
                    continue

                if not file_data:
                    results.append({
                        "filename": filename,
                        "status": "failed",
                        "error": "File is empty",
                    })
                    continue

                guessed_type = mimetypes.guess_type(filename)[0]

                try:
                    result = _ingest_image(
                        filename=filename,
                        content_type=guessed_type,
                        file_data=file_data,
                        db=db,
                    )
                    results.append(result)
                except HTTPException as e:
                    detail = e.detail if isinstance(e.detail, str) else str(e.detail)
                    results.append({
                        "filename": filename,
                        "status": "failed",
                        "error": detail,
                    })
                except Exception as exc:
                    logger.error(f"Failed to process {filename} from bulk upload: {exc}")
                    results.append({
                        "filename": filename,
                        "status": "failed",
                        "error": str(exc),
                    })

    except zipfile.BadZipFile:
        raise HTTPException(400, "Uploaded file is not a valid ZIP archive")

    return {"results": results, "total": len(results)}


def _ingest_image(
    *,
    filename: str,
    content_type: Optional[str],
    file_data: bytes,
    db: Session,
) -> dict:
    """Create or reuse a media record from raw image bytes"""
    detected_type = content_type or mimetypes.guess_type(filename)[0] or ""

    if not detected_type.startswith("image/"):
        raise HTTPException(400, f"File {filename} is not an image")

    file_size = len(file_data)
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if file_size > max_size:
        raise HTTPException(400, f"File {filename} exceeds max size")

    file_hash = hashlib.sha256(file_data).hexdigest()

    existing = db.query(Media).filter(Media.file_hash == file_hash).first()
    if existing:
        logger.info(f"File {filename} already exists (hash: {file_hash})")
        return {
            "filename": filename,
            "status": "duplicate",
            "media_id": existing.id
        }

    minio_key = f"images/{file_hash[:2]}/{file_hash}{_get_extension(filename, detected_type)}"

    upload_file(file_data, minio_key, detected_type)

    media = Media(
        file_hash=file_hash,
        minio_key=minio_key,
        filename=filename,
        content_type=detected_type,
        file_size=file_size,
        status="pending"
    )

    db.add(media)
    db.commit()
    db.refresh(media)

    job = task_queue.enqueue(
        analyze_image,
        media.id,
        job_timeout=settings.WORKER_TIMEOUT
    )

    logger.info(f"Uploaded {filename} (media_id: {media.id}, job_id: {job.id})")

    return {
        "filename": filename,
        "status": "uploaded",
        "media_id": media.id,
        "job_id": job.id
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
