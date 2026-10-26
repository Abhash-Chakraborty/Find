"""
Search endpoint for semantic image search
"""

import json
import time
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_required_user
from find_api.core.media_types import content_type_for_file_type
from find_api.core.runtime_profile import (
    bind_runtime,
    load_runtime_preferences,
    reset_runtime,
    resolve_runtime,
)
from find_api.ml.search_ranking import (
    bound_similarity,
    compute_textual_boost,
    extract_object_labels,
    rerank_results,
    tokenize,
)
from find_api.models.user import User
from find_api.routers.gallery import (
    build_original_url,
    build_thumbnail_url,
    parse_metadata_date,
)
from find_api.services.query_cache import get_cached_query, set_cached_query

router = APIRouter()

MOCK_SIMILARITY_THRESHOLD = -0.2
FULL_SIMILARITY_THRESHOLD = 0.38
# Nearest neighbours fetched from the index before thresholding and reranking.
SEARCH_CANDIDATE_POOL = 200
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
            clauses.append("AND content_type = :content_type")
            params["content_type"] = content_type_for_file_type(value)
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
            AND is_archived = false AND deleted_at IS NULL
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
    user: User | None = Depends(get_required_user),
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
    runtime = resolve_runtime(load_runtime_preferences(db))
    if runtime.applied_mode == "disabled":
        raise HTTPException(409, "AI search is disabled in instance settings.")
    if runtime.applied_mode == "unavailable":
        raise HTTPException(
            503,
            runtime.unavailable_reason
            or "The configured AI search runtime is unavailable.",
        )

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
        scoped_signature = (
            f"{index_signature}:scope={scope_user_id}:"
            f"runtime={runtime.applied_mode}:accel={runtime.configured_accel_mode}"
        )
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
    runtime_tokens = bind_runtime(runtime)
    try:
        if runtime.applied_mode == "mock":
            from find_api.ml.mock_embedder import get_mock_embedder

            embed_query = get_mock_embedder().embed_text
        elif runtime.applied_mode == "remote":
            # A remote deployment has no local CLIP to fall through to.
            from find_api.ml.remote_client import _feature_enabled, remote_embed_text

            if _feature_enabled("embed"):
                embed_query = remote_embed_text
            else:
                # Image vectors were produced by the mock embedder in this
                # configuration (see _remote_embed_image), so the query has to
                # come from the same space or nothing will match.
                from find_api.ml.mock_embedder import get_mock_embedder

                embed_query = get_mock_embedder().embed_text
        else:
            from find_api.ml.clip_embedder import get_clip_embedder

            embed_query = get_clip_embedder().embed_text

        t_embed_start = time.perf_counter()
        query_embedding = embed_query(q)
        embedding_ms = (time.perf_counter() - t_embed_start) * 1000
    finally:
        reset_runtime(runtime_tokens)

    # Convert to string format for pgvector
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Perform vector similarity search with pagination
    # Using cosine distance (1 - cosine similarity)
    # Added threshold to filter irrelevant results
    threshold = (
        MOCK_SIMILARITY_THRESHOLD
        if runtime.applied_mode == "mock"
        else FULL_SIMILARITY_THRESHOLD
    )

    # Rank in two steps so pgvector can use the HNSW index. The inner query is
    # a plain nearest-neighbour scan (ORDER BY distance LIMIT n), the only
    # shape the index serves; the outer query applies the similarity threshold
    # and the feedback boost to that pool. The boost is capped at +/-0.05
    # (workers/jobs.py), so a pool several pages deep holds the same top
    # results a full scan would.
    candidate_limit = max(SEARCH_CANDIDATE_POOL, (skip + limit + 1) * 2)
    query_sql = text(
        f"""
        WITH candidates AS (
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
                metadata_json,
                cluster_id,
                width,
                height,
                created_at,
                COALESCE(ranking_boost, 0) AS ranking_boost,
                vector <=> CAST(:embedding AS vector) AS distance
            FROM media
            WHERE status = 'indexed' AND vector IS NOT NULL
            AND is_hidden = false
            AND is_archived = false AND deleted_at IS NULL
            {metadata_filter_sql}
            {scope_clause}
            ORDER BY vector <=> CAST(:embedding AS vector)
            LIMIT :candidate_limit
        ),
        ranked AS (
            SELECT
                *,
                1 - distance AS similarity,
                1 - distance + ranking_boost AS final_score
            FROM candidates
            WHERE 1 - distance > :threshold
        )
        SELECT *, COUNT(*) OVER () AS total_matches
        FROM ranked
        ORDER BY final_score DESC, similarity DESC, id ASC
        LIMIT :limit OFFSET :skip
    """
    )

    t_retrieval_start = time.perf_counter()
    if db.get_bind().dialect.name == "postgresql":
        # An HNSW scan stops after hnsw.ef_search rows (40 by default), and
        # the WHERE filters drop some of those. An iterative scan keeps going
        # until the pool is full; relaxed order is fine because the outer
        # query sorts again.
        db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        ef_search = min(max(candidate_limit, 40), 1000)
        db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
    query_params = {
        "embedding": embedding_str,
        "candidate_limit": candidate_limit,
        "limit": limit,
        "skip": skip,
        "threshold": threshold,
        **metadata_filter_params,
    }
    if scope_user_id is not None:
        query_params["scope_user_id"] = scope_user_id
    result = db.execute(query_sql, query_params).all()
    retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000
    # Matches within the pool; it caps the count but never what a page shows.
    total_count = int(result[0].total_matches) if result else 0

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

        media_metadata["url"] = build_original_url(row.id)
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
            "ml_mode": runtime.applied_mode,
        }

    if not debug:
        set_cached_query(
            q,
            limit,
            skip,
            (
                f"{index_signature or ''}:scope={scope_user_id}:"
                f"runtime={runtime.applied_mode}:"
                f"accel={runtime.configured_accel_mode}"
            ),
            query_embedding,
            response,
            include_ocr=include_ocr,
            filter_key=filter_key,
        )

    return response
