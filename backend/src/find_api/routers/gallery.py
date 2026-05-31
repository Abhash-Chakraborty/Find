"""
Gallery endpoint for browsing images
"""

import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.queue import get_task_queue
from find_api.core.storage import get_file_url, delete_file
from find_api.models.media import Media
from find_api.models.cluster import Cluster
from find_api.services.query_cache import invalidate_query_cache
from find_api.workers.jobs import analyze_image, generate_thumbnail_for_media

logger = logging.getLogger(__name__)

router = APIRouter()

GalleryStatus = Literal["pending", "processing", "indexed", "failed"]


class BulkDeleteRequest(BaseModel):
    """Request body for deleting multiple media records."""

    media_ids: list[int] = Field(..., min_length=1, max_length=200)


class BulkDeleteResponse(BaseModel):
    """Summary of a bulk delete request."""

    message: str
    deleted_ids: list[int]
    missing_ids: list[int]
    failed_ids: list[int]
    deleted_count: int
    missing_count: int
    failed_count: int


class GalleryCountsResponse(BaseModel):
    """Status counts for the visible gallery tabs."""

    all: int
    indexed: int
    processing: int
    failed: int


def build_thumbnail_url(media_id: int) -> str:
    """Return the API route that serves the best available thumbnail."""
    return f"/api/image/{media_id}/thumbnail"


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


@router.get("/gallery/counts", response_model=GalleryCountsResponse)
def get_gallery_counts(
    liked: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Media).filter(Media.is_hidden.is_(False))
    if liked is not None:
        query = query.filter(Media.liked == liked)

    return GalleryCountsResponse(
        all=query.count(),
        indexed=query.filter(Media.status == "indexed").count(),
        processing=query.filter(Media.status == "processing").count(),
        failed=query.filter(Media.status == "failed").count(),
    )


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
    query = db.query(Media).filter(Media.is_hidden.is_(False))

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
            "processed_at": (
                media.processed_at.isoformat() if media.processed_at else None
            ),
            "width": media.width,
            "height": media.height,
            "file_size": media.file_size,
            "cluster_id": media.cluster_id,
            "minio_key": media.minio_key,
            "thumbnail_key": media.thumbnail_key,
            "thumbnail_content_type": media.thumbnail_content_type,
            "thumbnail_size": media.thumbnail_size,
            "thumbnail_width": media.thumbnail_width,
            "thumbnail_height": media.thumbnail_height,
            "liked": media.liked,
        }

        # Add original and thumbnail URLs separately.
        try:
            item["url"] = get_file_url(media.minio_key)
        except Exception:
            item["url"] = None
        item["thumbnail_url"] = build_thumbnail_url(media.id)

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
    row = (
        db.query(Media, Cluster.label)
        .outerjoin(Cluster, Media.cluster_id == Cluster.id)
        .filter(Media.id == media_id)
        .first()
    )

    if not row:
        raise HTTPException(404, "Image not found")

    media, cluster_label = row
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
        "cluster_label": cluster_label,
        "thumbnail_key": media.thumbnail_key,
        "thumbnail_content_type": media.thumbnail_content_type,
        "thumbnail_size": media.thumbnail_size,
        "thumbnail_width": media.thumbnail_width,
        "thumbnail_height": media.thumbnail_height,
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
    response["thumbnail_url"] = build_thumbnail_url(media.id)

    return response


@router.get("/image/{media_id}/thumbnail")
def get_image_thumbnail(media_id: int, db: Session = Depends(get_db)):
    """
    Get a redirect to the image file for use as a thumbnail.
    Returns a redirect to the MinIO presigned URL.
    """
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    object_key = media.thumbnail_key or media.minio_key

    try:
        url = get_file_url(object_key)
    except Exception:
        raise HTTPException(500, "Could not generate image URL")

    return RedirectResponse(url=url)


@router.post("/thumbnails/backfill")
def backfill_missing_thumbnails(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    Enqueue thumbnail-only jobs for existing images that do not have thumbnails.

    This is intentionally separate from reprocess so older libraries can get
    lightweight thumbnails without rerunning captions, detection, embeddings, or
    clustering.
    """
    media_list = (
        db.query(Media)
        .filter(Media.thumbnail_key.is_(None))
        .order_by(desc(Media.created_at))
        .limit(limit)
        .all()
    )

    if not media_list:
        return {
            "queued": 0,
            "remaining": 0,
            "job_ids": [],
            "message": "No missing thumbnails found.",
        }

    queue = get_task_queue("low")
    job_ids = []
    for media in media_list:
        job = queue.enqueue(
            generate_thumbnail_for_media,
            media.id,
            job_timeout=settings.WORKER_TIMEOUT,
            result_ttl=300,
        )
        job_ids.append(job.id)

    remaining = (
        db.query(Media)
        .filter(
            Media.thumbnail_key.is_(None), Media.id.notin_([m.id for m in media_list])
        )
        .count()
    )

    return {
        "queued": len(job_ids),
        "remaining": remaining,
        "job_ids": job_ids,
        "message": "Thumbnail backfill queued.",
    }


@router.post("/image/{media_id}/like")
def toggle_like(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    media.liked = not media.liked
    db.commit()
    invalidate_query_cache()
    db.refresh(media)

    return {"id": media.id, "liked": media.liked}


@router.post("/image/{media_id}/reprocess")
def reprocess_image(media_id: int, db: Session = Depends(get_db)):
    """
    Reset a media record to pending and re-enqueue analysis.

    Allowed for:
    - Images with status ``failed``
    - Images with status ``indexed`` that have incomplete metadata (no caption)
    - Images with status ``indexed`` that are missing a thumbnail
    """
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    metadata = normalize_metadata(media.metadata_json)
    is_indexed_incomplete = media.status == "indexed" and not metadata.get("caption")
    is_missing_thumbnail = media.status == "indexed" and not media.thumbnail_key

    if (
        media.status != "failed"
        and not is_indexed_incomplete
        and not is_missing_thumbnail
    ):
        raise HTTPException(
            400,
            "Reprocess is only available for failed images or indexed images "
            "with incomplete metadata or missing thumbnails.",
        )

    media.status = "pending"
    media.error_message = None
    media.processed_at = None

    try:
        job = get_task_queue().enqueue(
            analyze_image,
            media.id,
            True,
            job_timeout=settings.WORKER_TIMEOUT,
        )
        media.analysis_job_id = job.id
        db.commit()
        invalidate_query_cache()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(
            503, "Reprocess queue is unavailable. Please retry."
        ) from exc

    logger.info("Requeued analysis for media %s (job %s)", media.id, job.id)

    return {"media_id": media_id, "job_id": job.id, "status": "queued"}


def _remove_media_ids_from_clusters(db: Session, media_ids: set[int]) -> None:
    """Drop deleted media ids from every cluster that references them."""
    if not media_ids:
        return

    cluster_query = db.query(Cluster)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        cluster_query = cluster_query.filter(
            Cluster.member_ids.overlap(list(media_ids))
        )

    for cluster in cluster_query.all():
        current_members = cluster.member_ids or []
        if not any(member_id in media_ids for member_id in current_members):
            continue
        cluster.member_ids = [
            member_id for member_id in current_members if member_id not in media_ids
        ]
        cluster.member_count = len(cluster.member_ids)


def _delete_media_files(media: Media) -> None:
    """Delete original storage object and best-effort thumbnail object."""
    delete_file(media.minio_key)

    if media.thumbnail_key:
        try:
            delete_file(media.thumbnail_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Deleted original for media %s but failed to delete thumbnail %s: %s",
                media.id,
                media.thumbnail_key,
                exc,
            )


@router.delete("/image/{media_id}")
def delete_image(media_id: int, db: Session = Depends(get_db)):
    media = db.query(Media).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")

    try:
        _delete_media_files(media)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Failed to delete file from storage: {exc}") from exc

    db.delete(media)
    db.flush()

    _remove_media_ids_from_clusters(db, {media_id})

    db.commit()
    invalidate_query_cache()

    return {"message": "Image deleted", "id": media_id}


@router.post("/images/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_images(
    request: BulkDeleteRequest,
    db: Session = Depends(get_db),
):
    requested_ids = list(dict.fromkeys(request.media_ids))
    media_rows = db.query(Media).filter(Media.id.in_(requested_ids)).all()
    media_by_id = {media.id: media for media in media_rows}
    missing_ids = [
        media_id for media_id in requested_ids if media_id not in media_by_id
    ]
    deleted_ids: list[int] = []
    failed_ids: list[int] = []

    for media_id in requested_ids:
        media = media_by_id.get(media_id)
        if media is None:
            continue

        try:
            _delete_media_files(media)
        except Exception as exc:  # noqa: BLE001
            failed_ids.append(media_id)
            logger.warning(
                "Failed to delete media %s during bulk delete: %s", media_id, exc
            )
            continue

        db.delete(media)
        deleted_ids.append(media_id)

    if deleted_ids:
        db.flush()
        _remove_media_ids_from_clusters(db, set(deleted_ids))

    db.commit()
    if deleted_ids:
        invalidate_query_cache()

    return {
        "message": "Bulk delete completed",
        "deleted_ids": deleted_ids,
        "missing_ids": missing_ids,
        "failed_ids": failed_ids,
        "deleted_count": len(deleted_ids),
        "missing_count": len(missing_ids),
        "failed_count": len(failed_ids),
    }
