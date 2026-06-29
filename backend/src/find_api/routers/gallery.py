"""
Gallery endpoint for browsing images
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import (
    can_access_media,
    get_required_user,
    scope_media_query,
)
from find_api.core.queue import get_task_queue
from find_api.core.storage import get_file_url, delete_file
from find_api.models.media import Media
from find_api.models.cluster import Cluster
from find_api.models.user import User
from find_api.services.query_cache import invalidate_query_cache
from find_api.workers.jobs import analyze_image, generate_thumbnail_for_media

logger = logging.getLogger(__name__)

router = APIRouter()

GalleryStatus = Literal["pending", "processing", "indexed", "failed"]
SortOrder = Literal["newest", "oldest"]
DateRangePreset = Literal["last_30_days", "last_60_days", "last_90_days", "custom"]
OrientationFilter = Literal["landscape", "portrait", "square"]


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


class ArchiveRequest(BaseModel):
    """Request body for setting an asset's archive state."""

    archived: bool = True


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


def parse_date_range(
    preset: Optional[DateRangePreset] = None,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse date range parameters and return (start_date, end_date) in UTC.

    Args:
        preset: One of "last_30_days", "last_60_days", "last_90_days", or "custom"
        custom_start: ISO 8601 date string (YYYY-MM-DD) for custom range start
        custom_end: ISO 8601 date string (YYYY-MM-DD) for custom range end

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC, or (None, None) if no filtering
    """
    if not preset:
        return None, None

    now = datetime.now(timezone.utc)

    if preset == "last_30_days":
        start = now - timedelta(days=30)
        return start, now
    elif preset == "last_60_days":
        start = now - timedelta(days=60)
        return start, now
    elif preset == "last_90_days":
        start = now - timedelta(days=90)
        return start, now
    elif preset == "custom":
        start_date = None
        end_date = None

        try:
            if custom_start:
                start_date = datetime.strptime(custom_start, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid custom_start date: %s", custom_start)
            raise HTTPException(
                status_code=422,
                detail="Invalid date_start. Use YYYY-MM-DD.",
            ) from exc

        try:
            if custom_end:
                # End of day for the end date (23:59:59.999999)
                end_date = datetime.strptime(custom_end, "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    microsecond=999999,
                    tzinfo=timezone.utc,
                )
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid custom_end date: %s", custom_end)
            raise HTTPException(
                status_code=422,
                detail="Invalid date_end. Use YYYY-MM-DD.",
            ) from exc

        if start_date or end_date:
            # Normalize reversed date bounds
            if start_date and end_date and start_date > end_date:
                logger.warning(
                    "Custom date range inverted (start > end): %s > %s, swapping",
                    custom_start,
                    custom_end,
                )
                start_date, end_date = end_date, start_date
                # Correct time components after swap: earlier date should be 00:00:00, later date 23:59:59.999999
                start_date = start_date.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                end_date = end_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            return start_date, end_date

    return None, None


def parse_metadata_date(value: str | None, field_name: str) -> datetime | None:
    """Parse an ISO date/datetime query param into a timezone-aware datetime."""
    if not value:
        return None

    raw_value = value.strip()
    if not raw_value:
        return None

    is_date_only = "T" not in raw_value and ":" not in raw_value

    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, f"{field_name} must be a valid ISO date") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if field_name == "date_to" and is_date_only:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _public_media_query(db: Session):
    """Return media rows visible through public gallery/image routes.

    Filters only the vault ``is_hidden`` flag. Use for single-item lookups
    and for views (archive/trash) that intentionally surface archived or
    trashed assets. List/browse surfaces should use
    :func:`_browsable_media_query` instead.
    """
    return db.query(Media).filter(Media.is_hidden.is_(False))


def _browsable_media_query(db: Session):
    """Return media rows that belong in the main timeline/browse surfaces.

    Adds the asset-state scoping rule on top of the vault filter: an asset
    is browsable iff it is not hidden, not archived, and not trashed
    (``deleted_at IS NULL``). The dedicated archive/trash views must NOT use
    this helper — they filter on those columns directly.
    """
    return _public_media_query(db).filter(
        Media.is_archived.is_(False),
        Media.deleted_at.is_(None),
    )


def _serialize_media_item(media: Media) -> dict:
    """Build a gallery list item dict for one media row.

    Shared by the main gallery list and the archive/trash list views so the
    item shape stays consistent across surfaces.
    """
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
        "is_archived": media.is_archived,
        "deleted_at": media.deleted_at.isoformat() if media.deleted_at else None,
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

    return item


def _load_public_media_or_404(db: Session, media_id: int) -> Media:
    """Load a visible media row or raise 404."""
    media = _public_media_query(db).filter(Media.id == media_id).first()
    if not media:
        raise HTTPException(404, "Image not found")
    return media


def apply_metadata_filters(
    query,
    *,
    camera_make: str | None = None,
    camera_model: str | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
    file_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    orientation: OrientationFilter | None = None,
):
    """Apply shared metadata filters to a SQLAlchemy media query."""
    camera_make = camera_make.strip() if camera_make else None
    camera_model = camera_model.strip() if camera_model else None
    file_type = file_type.strip() if file_type else None

    if camera_make:
        query = query.filter(
            Media.exif_json["make"].as_string().ilike(f"%{camera_make}%")
        )
    if camera_model:
        query = query.filter(
            Media.exif_json["model"].as_string().ilike(f"%{camera_model}%")
        )
    if date_from is not None:
        query = query.filter(Media.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Media.created_at <= date_to)
    if min_width is not None:
        query = query.filter(Media.width >= min_width)
    if min_height is not None:
        query = query.filter(Media.height >= min_height)
    if orientation == "landscape":
        query = query.filter(Media.width > Media.height)
    elif orientation == "portrait":
        query = query.filter(Media.height > Media.width)
    elif orientation == "square":
        query = query.filter(Media.width == Media.height)
    if file_type:
        normalized_type = file_type.lower().lstrip(".")
        mime_type_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "tif": "image/tiff",
            "tiff": "image/tiff",
        }
        expected_content_type = mime_type_map.get(normalized_type, normalized_type)
        query = query.filter(Media.content_type == expected_content_type)
    return query


@router.get("/gallery/counts", response_model=GalleryCountsResponse)
def get_gallery_counts(
    liked: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    query = scope_media_query(_browsable_media_query(db), user)
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
    sort_order: SortOrder = Query(
        "newest",
        description="Sort by upload date: 'newest' (default) or 'oldest'",
    ),
    date_range: Optional[DateRangePreset] = Query(
        None,
        description="Date range preset: 'last_30_days', 'last_60_days', 'last_90_days', or 'custom'",
    ),
    date_start: Optional[str] = Query(
        None,
        description="Custom range start date (YYYY-MM-DD) when date_range='custom'",
    ),
    date_end: Optional[str] = Query(
        None,
        description="Custom range end date (YYYY-MM-DD) when date_range='custom'",
    ),
    camera_make: Optional[str] = Query(
        None,
        max_length=255,
        description="Filter by EXIF camera make",
    ),
    camera_model: Optional[str] = Query(
        None,
        max_length=255,
        description="Filter by EXIF camera model",
    ),
    min_width: Optional[int] = Query(None, ge=1, description="Minimum image width"),
    min_height: Optional[int] = Query(None, ge=1, description="Minimum image height"),
    file_type: Optional[str] = Query(
        None,
        max_length=20,
        description="Filter by image file type",
    ),
    date_from: Optional[str] = Query(
        None,
        description="Filter to media uploaded on or after this ISO date",
    ),
    date_to: Optional[str] = Query(
        None,
        description="Filter to media uploaded on or before this ISO date",
    ),
    orientation: Optional[OrientationFilter] = Query(
        None,
        description="Filter by image orientation",
    ),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Get paginated list of images with optional date filtering and sorting.

    Args:
        skip: Number of records to skip
        limit: Max number of records to return
        status: Filter by status (pending, processing, indexed, failed)
        liked: Filter by like status (true/false)
        sort_order: Sort by upload date ('newest' or 'oldest')
        date_range: Date range preset or 'custom'
        date_start: Custom range start (YYYY-MM-DD)
        date_end: Custom range end (YYYY-MM-DD)

    Returns:
        Paginated list of media records
    """
    # Build query
    query = scope_media_query(_browsable_media_query(db), user)

    if status:
        query = query.filter(Media.status == status)
    if liked is not None:
        query = query.filter(Media.liked == liked)
    parsed_date_from = parse_metadata_date(date_from, "date_from")
    parsed_date_to = parse_metadata_date(date_to, "date_to")
    if (
        parsed_date_from is not None
        and parsed_date_to is not None
        and parsed_date_from > parsed_date_to
    ):
        raise HTTPException(422, "date_from must be before or equal to date_to")

    query = apply_metadata_filters(
        query,
        camera_make=camera_make,
        camera_model=camera_model,
        min_width=min_width,
        min_height=min_height,
        file_type=file_type,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
        orientation=orientation,
    )

    # Apply date range filter if specified
    start_date, end_date = parse_date_range(date_range, date_start, date_end)
    if start_date or end_date:
        filters = []
        if start_date:
            filters.append(Media.created_at >= start_date)
        if end_date:
            filters.append(Media.created_at <= end_date)
        if filters:
            query = query.filter(and_(*filters))

    # Get total count
    total = query.count()

    # Apply sorting (newest first is default)
    if sort_order == "oldest":
        query = query.order_by(Media.created_at)
    else:
        query = query.order_by(desc(Media.created_at))

    # Get paginated results
    media_list = query.offset(skip).limit(limit).all()

    # Build response
    items = [_serialize_media_item(media) for media in media_list]

    page = (skip // limit) + 1 if limit else 1
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "page": page,
        "limit": limit,
    }


@router.get("/image/{media_id}")
def get_image_detail(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
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
        .filter(Media.id == media_id, Media.is_hidden.is_(False))
        .first()
    )

    if not row:
        raise HTTPException(404, "Image not found")

    media, cluster_label = row
    if not can_access_media(media, user):
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
def get_image_thumbnail(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Get a redirect to the image file for use as a thumbnail.
    Returns a redirect to the MinIO presigned URL.
    """
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
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
    user: Optional[User] = Depends(get_required_user),
):
    """
    Enqueue thumbnail-only jobs for existing images that do not have thumbnails.

    This is intentionally separate from reprocess so older libraries can get
    lightweight thumbnails without rerunning captions, detection, embeddings, or
    clustering.
    """
    media_list = (
        scope_media_query(
            _public_media_query(db).filter(Media.thumbnail_key.is_(None)), user
        )
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

    remaining = scope_media_query(
        _public_media_query(db).filter(
            Media.thumbnail_key.is_(None),
            Media.id.notin_([m.id for m in media_list]),
        ),
        user,
    ).count()

    return {
        "queued": len(job_ids),
        "remaining": remaining,
        "job_ids": job_ids,
        "message": "Thumbnail backfill queued.",
    }


@router.post("/image/{media_id}/like")
def toggle_like(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
        raise HTTPException(404, "Image not found")

    media.liked = not media.liked
    db.commit()
    invalidate_query_cache()
    db.refresh(media)

    return {"id": media.id, "liked": media.liked}


@router.post("/image/{media_id}/archive")
def set_archive(
    media_id: int,
    request: ArchiveRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Archive or unarchive an asset.

    Archived assets are kept but excluded from the main timeline/search; they
    remain visible in the dedicated archive view. A trashed asset cannot be
    archived — restore it first.
    """
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
        raise HTTPException(404, "Image not found")
    if media.deleted_at is not None:
        raise HTTPException(409, "Cannot archive a trashed image; restore it first.")

    media.is_archived = bool(request.archived)
    db.commit()
    invalidate_query_cache()
    db.refresh(media)

    return {"id": media.id, "is_archived": media.is_archived}


@router.post("/image/{media_id}/trash")
def trash_image(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Soft-delete (trash) an asset.

    Sets ``deleted_at`` so the asset drops out of every browse surface but is
    recoverable via restore until purged. The file is NOT removed from storage
    (that only happens on permanent delete / empty-trash).
    """
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
        raise HTTPException(404, "Image not found")

    if media.deleted_at is None:
        media.deleted_at = datetime.now(timezone.utc)
        db.commit()
        invalidate_query_cache()
        db.refresh(media)

    return {
        "id": media.id,
        "deleted_at": media.deleted_at.isoformat() if media.deleted_at else None,
    }


@router.post("/image/{media_id}/restore")
def restore_image(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Restore a trashed asset back to the timeline."""
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
        raise HTTPException(404, "Image not found")

    media.deleted_at = None
    db.commit()
    invalidate_query_cache()
    db.refresh(media)

    return {"id": media.id, "deleted_at": None}


@router.get("/archive")
def get_archive(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """List archived assets (archived and not trashed), newest first."""
    query = scope_media_query(
        _public_media_query(db).filter(
            Media.is_archived.is_(True),
            Media.deleted_at.is_(None),
        ),
        user,
    )
    total = query.count()
    media_list = query.order_by(desc(Media.created_at)).offset(skip).limit(limit).all()
    items = [_serialize_media_item(media) for media in media_list]
    page = (skip // limit) + 1 if limit else 1
    return {"items": items, "total": total, "skip": skip, "page": page, "limit": limit}


@router.get("/trash")
def get_trash(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """List trashed assets (``deleted_at`` set), most recently trashed first."""
    query = scope_media_query(
        _public_media_query(db).filter(Media.deleted_at.isnot(None)),
        user,
    )
    total = query.count()
    media_list = query.order_by(desc(Media.deleted_at)).offset(skip).limit(limit).all()
    items = [_serialize_media_item(media) for media in media_list]
    page = (skip // limit) + 1 if limit else 1
    return {"items": items, "total": total, "skip": skip, "page": page, "limit": limit}


@router.post("/trash/empty", response_model=BulkDeleteResponse)
def empty_trash(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Permanently delete every trashed asset (files + rows).

    This is the only place trashing becomes irreversible. Mirrors the bulk
    delete flow: best-effort storage deletion, then row removal and cluster
    membership cleanup.
    """
    media_rows = scope_media_query(
        _public_media_query(db).filter(Media.deleted_at.isnot(None)),
        user,
    ).all()

    deleted_ids: list[int] = []
    failed_ids: list[int] = []

    for media in media_rows:
        try:
            _delete_media_files(media)
        except Exception as exc:  # noqa: BLE001
            failed_ids.append(media.id)
            logger.warning(
                "Failed to delete media %s during empty-trash: %s", media.id, exc
            )
            continue
        db.delete(media)
        deleted_ids.append(media.id)

    if deleted_ids:
        db.flush()
        _remove_media_ids_from_clusters(db, set(deleted_ids))

    db.commit()
    if deleted_ids:
        invalidate_query_cache()

    return {
        "message": "Trash emptied",
        "deleted_ids": deleted_ids,
        "missing_ids": [],
        "failed_ids": failed_ids,
        "deleted_count": len(deleted_ids),
        "missing_count": 0,
        "failed_count": len(failed_ids),
    }


@router.post("/trash/purge", response_model=BulkDeleteResponse)
def purge_expired_trash(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Permanently delete trashed assets older than the retention window.

    Like empty-trash but age-bounded: only rows whose ``deleted_at`` is older
    than ``TRASH_RETENTION_DAYS`` are removed. Intended for a scheduled/manual
    auto-purge. Retention of 0 disables age-based purging (no-op).
    """
    retention_days = settings.TRASH_RETENTION_DAYS
    if retention_days <= 0:
        return {
            "message": "Auto-purge disabled (TRASH_RETENTION_DAYS=0)",
            "deleted_ids": [],
            "missing_ids": [],
            "failed_ids": [],
            "deleted_count": 0,
            "missing_count": 0,
            "failed_count": 0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    media_rows = scope_media_query(
        _public_media_query(db).filter(
            Media.deleted_at.isnot(None),
            Media.deleted_at < cutoff,
        ),
        user,
    ).all()

    deleted_ids: list[int] = []
    failed_ids: list[int] = []

    for media in media_rows:
        try:
            _delete_media_files(media)
        except Exception as exc:  # noqa: BLE001
            failed_ids.append(media.id)
            logger.warning(
                "Failed to delete media %s during trash purge: %s", media.id, exc
            )
            continue
        db.delete(media)
        deleted_ids.append(media.id)

    if deleted_ids:
        db.flush()
        _remove_media_ids_from_clusters(db, set(deleted_ids))

    db.commit()
    if deleted_ids:
        invalidate_query_cache()

    return {
        "message": f"Purged trash older than {retention_days} days",
        "deleted_ids": deleted_ids,
        "missing_ids": [],
        "failed_ids": failed_ids,
        "deleted_count": len(deleted_ids),
        "missing_count": 0,
        "failed_count": len(failed_ids),
    }


@router.post("/image/{media_id}/reprocess")
def reprocess_image(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Reset a media record to pending and re-enqueue analysis.

    Allowed for:
    - Images with status ``failed``
    - Images with status ``indexed`` that have incomplete metadata (no caption)
    - Images with status ``indexed`` that are missing a thumbnail
    """
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
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
def delete_image(
    media_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    media = _load_public_media_or_404(db, media_id)
    if not can_access_media(media, user):
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
    user: Optional[User] = Depends(get_required_user),
):
    requested_ids = list(dict.fromkeys(request.media_ids))
    media_rows = scope_media_query(
        _public_media_query(db).filter(Media.id.in_(requested_ids)), user
    ).all()
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
