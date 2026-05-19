"""
Gallery endpoint for browsing images
"""

import json
import logging
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.queue import get_task_queue
from find_api.core.storage import get_file_url, delete_file
from find_api.models.media import Media
from find_api.models.cluster import Cluster
from find_api.workers.jobs import analyze_image

logger = logging.getLogger(__name__)

router = APIRouter()

GalleryStatus = Literal["pending", "processing", "indexed", "failed"]


def normalize_metadata(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


@router.get("/gallery")
def get_gallery(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[GalleryStatus] = Query(
        None,
        description="Filter by processing status",
    ),
    liked: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """
    Get paginated list of images

    Args:
        skip: Number of records to skip
        limit: Max number of records to return
        status: Filter by status (pending, processing, indexed, failed)

    Returns:
        Paginated list of media records
    """
    # Build query
    query = db.query(Media)

    if status:
        query = query.filter(Media.status == status)
    if liked is not None:
        query = query.filter(Media.liked == liked)

    # Get total count
    total = query.count()

    # Get paginated results
    media_list = query.order_by(desc(Media.created_at)).offset(skip).limit(limit).all()

    # Build response
    items = []
    for media in media_list:
        item = {
            "id": media.id,
            "filename": media.filename,
            "status": media.status,
            "created_at": media.created_at.isoformat() if media.created_at else None,
            "processed_at": media.processed_at.isoformat()
            if media.processed_at
            else None,
            "width": media.width,
            "height": media.height,
            "file_size": media.file_size,
            "cluster_id": media.cluster_id,
            "minio_key": media.minio_key,
            "liked": media.liked,
        }

        # Add thumbnail URL
        try:
            item["url"] = get_file_url(media.minio_key)
        except Exception:
            item["url"] = None

        # Add metadata if indexed
        metadata = normalize_metadata(media.metadata_json)
        if media.status == "indexed" and metadata:
            item["caption"] = metadata.get("caption", "")
            item["objects"] = metadata.get("objects", [])
            item["has_text"] = bool(metadata.get("ocr_text", ""))

        items.append(item)

    page = (skip // limit) + 1 if limit else 1
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "page": page,
        "limit": limit,
    }


@router.get("/image/{media_id}")
def get_image_detail(media_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific image

    Args:
        media_id: Media record ID

    Returns:
        Complete media information including metadata
    """
    media = db.query(Media).filter(Media.id == media_id).first()

    if not media:
        from fastapi import HTTPException

        raise HTTPException(404, "Image not found")

    metadata = normalize_metadata(media.metadata_json)

    # Build response
    response = {
        "id": media.id,
        "filename": media.filename,
        "minio_key": media.minio_key,
        "file_hash": media.file_hash,
        "status": media.status,
        "content_type": media.content_type,
        "file_size": media.file_size,
        "width": media.width,
        "height": media.height,
        "created_at": media.created_at.isoformat() if media.created_at else None,
        "processed_at": media.processed_at.isoformat() if media.processed_at else None,
        "cluster_id": media.cluster_id,
        "metadata": metadata,
        "caption": metadata.get("caption", ""),
        "objects": metadata.get("objects", []),
        "has_text": bool(metadata.get("ocr_text", "")),
        "exif": media.exif_json,
        "error": media.error_message,
        "liked": media.liked,
    }

    # Add presigned URL
    try:
        response["url"] = get_file_url(media.minio_key)
    except Exception:
        response["url"] = None

    return response


@router.post("/image/{media_id}/like")
def toggle_like(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    media.liked = not media.liked
    db.commit()
    db.refresh(media)

    return {"id": media.id, "liked": media.liked}


@router.post("/image/{media_id}/reprocess")
def reprocess_image(media_id: int, db: Session = Depends(get_db)):
    """
    Reset a media record to pending and re-enqueue analysis.

    Allowed for:
    - Images with status ``failed``
    - Images with status ``indexed`` that have incomplete metadata (no caption)
    """
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    metadata = normalize_metadata(media.metadata_json)
    is_indexed_incomplete = media.status == "indexed" and not metadata.get("caption")

    if media.status != "failed" and not is_indexed_incomplete:
        raise HTTPException(
            400,
            "Reprocess is only available for failed images or indexed images with incomplete metadata.",
        )

    media.status = "pending"
    media.error_message = None
    media.processed_at = None

    try:
        job = get_task_queue().enqueue(
            analyze_image, media.id, job_timeout=settings.WORKER_TIMEOUT
        )
        media.analysis_job_id = job.id
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            503, "Reprocess queue is unavailable. Please retry."
        ) from exc

    logger.info("Requeued analysis for media %s (job %s)", media.id, job.id)

    return {"media_id": media_id, "job_id": job.id, "status": "queued"}


@router.delete("/image/{media_id}")
def delete_image(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    try:
        delete_file(media.minio_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Failed to delete file from storage: {exc}") from exc

    db.delete(media)
    db.flush()

    clusters = db.query(Cluster).filter(Cluster.member_ids.contains([media_id])).all()
    for cluster in clusters:
        current_members = cluster.member_ids or []
        if media_id in current_members:
            cluster.member_ids = [
                member_id for member_id in current_members if member_id != media_id
            ]
            cluster.member_count = len(cluster.member_ids)

    db.commit()

    return {"message": "Image deleted", "id": media_id}
