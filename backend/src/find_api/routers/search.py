"""
Search endpoint for semantic image search
"""

import json
import time
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.models.user import User
from find_api.ml.search_ranking import (
    bound_similarity,
    compute_textual_boost,
    extract_object_labels,
    rerank_results,
    tokenize,
)
from find_api.core.storage import get_file_url
from find_api.routers.gallery import build_thumbnail_url, parse_metadata_date
from find_api.services.query_cache import get_cached_query, set_cached_query
from typing import Optional

router = APIRouter()

MOCK_SIMILARITY_THRESHOLD = -0.2
FULL_SIMILARITY_THRESHOLD = 0.38
OrientationFilter = Literal["landscape", "portrait", "square"]


def _metadata_filter_sql(
    *,
    camera_make: str | None,
    camera_model: str | None,
    min_width: int | None,
    min_height: int | None,
    file_type: str | None,
    date_from: str | None,
    date_to: str | None,
    orientation: OrientationFilter | None,
) -> tuple[str, dict[str, Any], str]:
    """Build safe metadata filter SQL and cache-key data for search."""
    parsed_date_from = parse_metadata_date(date_from, "date_from")
    parsed_date_to = parse_metadata_date(date_to, "date_to")
    if (
        parsed_date_from is not None
        and parsed_date_to is not None
        and parsed_date_from > parsed_date_to
    ):
        from fastapi import HTTPException

        raise HTTPException(422, "date_from must be before or equal to date_to")

    clauses: list[str] = []
    params: dict[str, Any] = {}
    filter_parts: list[str] = []

    def add_filter_part(key: str, value: object) -> None:
        filter_parts.append(f"{key}={quote(str(value), safe='')}")

    if camera_make:
        value = camera_make.strip()
        if value:
            clauses.append("AND exif_json ->> 'make' ILIKE :camera_make_pattern")
            params["camera_make_pattern"] = f"%{value}%"
            add_filter_part("camera_make", value.lower())

    if camera_model:
        value = camera_model.strip()
        if value:
            clauses.append("AND exif_json ->> 'model' ILIKE :camera_model_pattern")
            params["camera_model_pattern"] = f"%{value}%"
            add_filter_part("camera_model", value.lower())

    if parsed_date_from is not None:
        clauses.append("AND created_at >= :date_from")
        params["date_from"] = parsed_date_from
        add_filter_part("date_from", parsed_date_from.isoformat())

    if parsed_date_to is not None:
        clauses.append("AND created_at <= :date_to")
        params["date_to"] = parsed_date_to
        add_filter_part("date_to", parsed_date_to.isoformat())

    if min_width is not None:
        clauses.append("AND width >= :min_width")
        params["min_width"] = min_width
        add_filter_part("min_width", min_width)

    if min_height is not None:
        clauses.append("AND height >= :min_height")
        params["min_height"] = min_height
        add_filter_part("min_height", min_height)

    if orientation == "landscape":
        clauses.append("AND width > height")
        add_filter_part("orientation", "landscape")
    elif orientation == "portrait":
        clauses.append("AND height > width")
        add_filter_part("orientation", "portrait")
    elif orientation == "square":
        clauses.append("AND width = height")
        add_filter_part("orientation", "square")

    if file_type:
        value = file_type.strip().lower().lstrip(".")
        if value:
            clauses.append("AND content_type ILIKE :file_type_pattern")
            params["file_type_pattern"] = f"%{value}%"
            add_filter_part("file_type", value)

    return "\n        ".join(clauses), params, "&".join(sorted(filter_parts))


def _search_index_signature(db: Session) -> str:
    """Return a small DB-backed signature for search-visible indexed media."""
    signature_result = db.execute(
        text(
            """
            SELECT COUNT(*) AS indexed_count, MAX(processed_at) AS max_processed_at
            FROM media
            WHERE status = 'indexed' AND vector IS NOT NULL AND is_hidden = false
        """
        )
    )
    row = signature_result.mappings().first() or {}
    max_processed = row.get("max_processed_at")
    if hasattr(max_processed, "isoformat"):
        max_processed = max_processed.isoformat()
    return f"{row.get('indexed_count', 0)}:{max_processed or ''}"


@router.get("/search")
def search_images(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(24, ge=1, le=100, description="Maximum results to return"),
    skip: int = Query(0, ge=0, description="Number of results to skip"),
    include_ocr: bool = Query(
        False,
        description="Include raw OCR text in response metadata (disabled by default)",
    ),
    camera_make: str | None = Query(
        None,
        max_length=255,
        description="Filter by EXIF camera make",
    ),
    camera_model: str | None = Query(
        None,
        max_length=255,
        description="Filter by EXIF camera model",
    ),
    min_width: int | None = Query(None, ge=1, description="Minimum image width"),
    min_height: int | None = Query(None, ge=1, description="Minimum image height"),
    file_type: str | None = Query(
        None,
        max_length=20,
        description="Filter by image file type",
    ),
    date_from: str | None = Query(
        None,
        description="Filter to media uploaded on or after this ISO date",
    ),
    date_to: str | None = Query(
        None,
        description="Filter to media uploaded on or before this ISO date",
    ),
    orientation: OrientationFilter | None = Query(
        None,
        description="Filter by image orientation",
    ),
    debug: bool = Query(False, description="Include retrieval diagnostics in response"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """
    Semantic search for images using natural language with pagination support.

    Args:
        q: Search query (natural language)
        limit: Maximum number of results (default: 24, max: 100)
        skip: Number of results to skip for pagination (default: 0)
        include_ocr: Return OCR text in response metadata when true

    Returns:
        Paginated list of matching images with metadata for frontend navigation.
    """
    t_total_start = time.perf_counter()
    metadata_filter_sql, metadata_filter_params, filter_key = _metadata_filter_sql(
        camera_make=camera_make,
        camera_model=camera_model,
        min_width=min_width,
        min_height=min_height,
        file_type=file_type,
        date_from=date_from,
        date_to=date_to,
        orientation=orientation,
    )

    # Restrict results to the caller's own media in shared mode (IDOR guard).
    # Local mode (user is None) and admins are unrestricted.
    scope_user_id = user.id if (user is not None and user.role != "admin") else None
    scope_clause = (
        " AND uploader_user_id = :scope_user_id" if scope_user_id is not None else ""
    )

    # Keep debug requests uncached so timing diagnostics describe the actual path.
    index_signature = None
    if not debug:
        index_signature = _search_index_signature(db)
        # Partition the cache by scope so one user cannot read another's
        # cached results in shared mode.
        scoped_signature = f"{index_signature}:scope={scope_user_id}"
        cached = get_cached_query(
            q,
            limit,
            skip,
            scoped_signature,
            include_ocr=include_ocr,
            filter_key=filter_key,
        )
        if cached is not None:
            return cached["response"]

    # Generate query embedding
    if settings.ML_MODE.lower() == "mock":
        from find_api.ml.mock_embedder import get_mock_embedder

        embedder = get_mock_embedder()
    else:
        from find_api.ml.clip_embedder import get_clip_embedder

        embedder = get_clip_embedder()

    t_embed_start = time.perf_counter()
    query_embedding = embedder.embed_text(q)
    embedding_ms = (time.perf_counter() - t_embed_start) * 1000

    # Convert to string format for pgvector
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Perform vector similarity search with pagination
    # Using cosine distance (1 - cosine similarity)
    # Added threshold to filter irrelevant results
    threshold = (
        MOCK_SIMILARITY_THRESHOLD
        if settings.ML_MODE.lower() == "mock"
        else FULL_SIMILARITY_THRESHOLD
    )

    # First get total count of matching results
    count_query = text(
        f"""
        SELECT COUNT(*) as total
        FROM media
        WHERE status = 'indexed' AND vector IS NOT NULL
        AND is_hidden = false
        {metadata_filter_sql}
        AND 1 - (vector <=> CAST(:embedding AS vector)) > :threshold
        {scope_clause}
    """
    )
    count_params = {
        "embedding": embedding_str,
        "threshold": threshold,
        **metadata_filter_params,
    }
    if scope_user_id is not None:
        count_params["scope_user_id"] = scope_user_id
    count_result = db.execute(count_query, count_params)
    total_count = count_result.scalar() or 0

    # Get paginated results
    query_sql = text(
        f"""
        WITH ranked_results AS (
            SELECT
                id,
                filename,
                minio_key,
                thumbnail_key,
                thumbnail_content_type,
                thumbnail_size,
                thumbnail_width,
                thumbnail_height,
                status,
                liked,
                is_hidden,
                metadata_json,
                cluster_id,
                width,
                height,
                created_at,
                1 - (vector <=> CAST(:embedding AS vector)) as similarity,
                COALESCE(ranking_boost, 0) as ranking_boost,
                (
                    1 - (vector <=> CAST(:embedding AS vector))
                    + COALESCE(ranking_boost, 0)
                ) as final_score
            FROM media
            WHERE status = 'indexed' AND vector IS NOT NULL
            {metadata_filter_sql}
            {scope_clause}
        )
        SELECT * FROM ranked_results
        WHERE similarity > :threshold AND is_hidden = false
        ORDER BY final_score DESC, similarity DESC, id ASC
        LIMIT :limit OFFSET :skip
    """
    )

    t_retrieval_start = time.perf_counter()
    query_params = {
        "embedding": embedding_str,
        "limit": limit,
        "skip": skip,
        "threshold": threshold,
        **metadata_filter_params,
    }
    if scope_user_id is not None:
        query_params["scope_user_id"] = scope_user_id
    result = db.execute(query_sql, query_params)
    retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000

    # Build response
    query_tokens = tokenize(q)
    results = []
    for row in result:
        metadata_payload: dict[str, object] = {}

        # Safely coerce metadata_json into dict
        raw_metadata = row.metadata_json
        if raw_metadata:
            if isinstance(raw_metadata, dict):
                metadata_payload = raw_metadata
            else:
                try:
                    metadata_payload = json.loads(raw_metadata)
                except (TypeError, json.JSONDecodeError):
                    metadata_payload = {}

        if not isinstance(metadata_payload, dict):
            metadata_payload = {}

        # Build metadata object compatible with frontend expectations
        caption_text = str(metadata_payload.get("caption") or "")
        ocr_text = str(metadata_payload.get("ocr_text") or "")

        objects_payload = metadata_payload.get("objects") or []
        object_labels = extract_object_labels(objects_payload)

        media_metadata = {
            "id": row.id,
            "filename": row.filename,
            "minio_key": row.minio_key,
            "thumbnail_key": row.thumbnail_key,
            "thumbnail_content_type": row.thumbnail_content_type,
            "thumbnail_size": row.thumbnail_size,
            "thumbnail_width": row.thumbnail_width,
            "thumbnail_height": row.thumbnail_height,
            "status": row.status,
            "liked": bool(row.liked),
            "width": row.width,
            "height": row.height,
            "cluster_id": row.cluster_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "caption": caption_text or None,
            "objects": metadata_payload.get("objects") or [],
        }

        if include_ocr:
            media_metadata["ocr_text"] = ocr_text or None

        try:
            media_metadata["url"] = get_file_url(row.minio_key)
        except Exception:
            media_metadata["url"] = None
        media_metadata["thumbnail_url"] = build_thumbnail_url(row.id)

        vector_similarity = float(row.similarity)
        textual_boost = compute_textual_boost(
            query_tokens=query_tokens,
            caption=caption_text,
            ocr_text=ocr_text,
            object_labels=object_labels,
        )
        final_similarity = bound_similarity(vector_similarity + textual_boost)

        results.append(
            {
                "media_id": row.id,
                "similarity": final_similarity,
                "metadata": media_metadata,
                "_vector_similarity": vector_similarity,
            }
        )

    # OCR/text-aware reranking within the retrieved candidate set.
    rerank_results(results)

    # Calculate pagination metadata
    page = (skip // limit) + 1 if limit > 0 else 1
    has_more = (skip + len(results)) < total_count

    total_ms = (time.perf_counter() - t_total_start) * 1000

    response: dict[str, Any] = {
        "query": q,
        "results": results,
        "total": total_count,
        "page": page,
        "limit": limit,
        "skip": skip,
        "has_more": has_more,
    }

    debug_enabled = debug and settings.ENVIRONMENT.lower() in {"local", "development"}
    if debug_enabled:
        response["diagnostics"] = {
            "embedding_ms": round(embedding_ms, 2),
            "retrieval_ms": round(retrieval_ms, 2),
            "total_ms": round(total_ms, 2),
            "results_returned": len(results),
            "similarity_threshold": threshold,
            "ml_mode": settings.ML_MODE,
        }

    if not debug:
        set_cached_query(
            q,
            limit,
            skip,
            f"{index_signature or ''}:scope={scope_user_id}",
            query_embedding,
            response,
            include_ocr=include_ocr,
            filter_key=filter_key,
        )

    return response
