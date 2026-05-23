"""
Search endpoint for semantic image search
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from typing import Dict

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.storage import get_file_url
from find_api.routers.gallery import build_thumbnail_url

router = APIRouter()


@router.get("/search")
def search_images(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Semantic search for images using natural language

    Args:
        q: Search query (natural language)
        limit: Maximum number of results

    Returns:
        Ranked list of matching images
    """
    # Generate query embedding
    if settings.ML_MODE.lower() == "mock":
        from find_api.ml.mock_embedder import get_mock_embedder

        embedder = get_mock_embedder()
    else:
        from find_api.ml.clip_embedder import get_clip_embedder

        embedder = get_clip_embedder()

    query_embedding = embedder.embed_text(q)

    # Convert to string format for pgvector
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Perform vector similarity search
    # Using cosine distance (1 - cosine similarity)
    # Added threshold to filter irrelevant results
    query_sql = text(
        """
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
                metadata_json,
                cluster_id,
                width,
                height,
                created_at,
                1 - (vector <=> CAST(:embedding AS vector)) as similarity
            FROM media
            WHERE status = 'indexed' AND vector IS NOT NULL
        )
        SELECT * FROM ranked_results
        WHERE similarity > :threshold
        ORDER BY similarity DESC
        LIMIT :limit
    """
    )

    # SigLIP similarities can be lower than OpenAI CLIP.
    # Lowering threshold to ensure results are returned.
    threshold = -1.0 if settings.ML_MODE.lower() == "mock" else 0.45

    result = db.execute(
        query_sql, {"embedding": embedding_str, "limit": limit, "threshold": threshold}
    )

    # Build response
    results = []
    for row in result:
        metadata_payload: Dict[str, object] = {}

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
            "caption": metadata_payload.get("caption") or None,
            "objects": metadata_payload.get("objects") or [],
        }

        try:
            media_metadata["url"] = get_file_url(row.minio_key)
        except Exception:
            media_metadata["url"] = None
        media_metadata["thumbnail_url"] = build_thumbnail_url(row.id)

        results.append(
            {
                "media_id": row.id,
                "similarity": float(row.similarity),
                "metadata": media_metadata,
            }
        )

    return {"query": q, "results": results, "total": len(results)}
