"""Candidate sources that feed the Track C variants (issue #99).

A source turns query text into a pool of `Candidate` rows. It owns the parts
that need a real environment — model weights and a populated database — which
is exactly why it is separated from the ranking rules in `variants.py`: those
stay pure and unit-testable, and this module is the only thing a benchmark run
has to stand up.

Imports of the database and ML stack are deferred into the functions that need
them, so `find_api.evaluation` stays importable in a bare test environment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Sequence

from find_api.evaluation.variants import Candidate

# Mirrors the projection in routers/search.py, plus the signals only Track C
# uses (liked, created_at, album membership). `metadata_json` carries caption,
# ocr_text, and objects, so the boost inputs come from the same place
# production reads them from.
CANDIDATE_SQL = """
    SELECT
        m.id,
        1 - (m.vector <=> CAST(:embedding AS vector)) AS similarity,
        COALESCE(m.ranking_boost, 0) AS ranking_boost,
        m.liked,
        m.created_at,
        m.metadata_json,
        (
            SELECT COUNT(*) FROM album_assets aa WHERE aa.media_id = m.id
        ) AS album_count
    FROM media m
    WHERE m.status = 'indexed' AND m.vector IS NOT NULL
      AND m.is_hidden = false
      AND m.is_archived = false AND m.deleted_at IS NULL
    ORDER BY m.vector <=> CAST(:embedding AS vector)
    LIMIT :limit
"""


def _coerce_metadata(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    import json

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def row_to_candidate(row: Any) -> Candidate:
    """Build a Candidate from a search result row."""
    from find_api.ml.search_ranking import extract_object_labels

    metadata = _coerce_metadata(row.metadata_json)
    created_at = row.created_at
    if created_at is not None and not isinstance(created_at, datetime):
        created_at = None

    return Candidate(
        media_id=str(row.id),
        vector_similarity=float(row.similarity),
        caption=str(metadata.get("caption") or ""),
        ocr_text=str(metadata.get("ocr_text") or ""),
        object_labels=tuple(extract_object_labels(metadata.get("objects") or [])),
        ranking_boost=float(row.ranking_boost or 0.0),
        liked=bool(row.liked),
        created_at=created_at,
        album_count=int(row.album_count or 0),
    )


def postgres_candidate_source(
    session_factory: Callable[[], Any],
    embed_text: Callable[[str], Sequence[float]],
    *,
    exact: bool = True,
) -> Callable[[str, int], list[Candidate]]:
    """Candidate source backed by pgvector.

    `exact=True` disables index scans for the duration of the query, which the
    benchmark protocol requires: an HNSW index is deployed, so without this the
    pool is approximate and ANN recall error would be silently attributed to
    whichever ranking rule happened to be under test. Track A measures the
    approximation on purpose; Track C must not absorb it by accident.

    The setting is `SET LOCAL`, so it is scoped to the transaction and cannot
    leak into anything else using the same connection.
    """
    from sqlalchemy import text as sql_text

    def _retrieve(query_text: str, pool_size: int) -> list[Candidate]:
        embedding = embed_text(query_text)
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        session = session_factory()
        try:
            with session.begin():
                if exact:
                    # Bitmap scans are disabled alongside index scans because
                    # either one can reach the HNSW index; leaving bitmap on
                    # would make "exact" true only most of the time.
                    session.execute(sql_text("SET LOCAL enable_indexscan = off"))
                    session.execute(sql_text("SET LOCAL enable_bitmapscan = off"))
                rows = session.execute(
                    sql_text(CANDIDATE_SQL),
                    {"embedding": embedding_str, "limit": pool_size},
                ).all()
            return [row_to_candidate(row) for row in rows]
        finally:
            session.close()

    return _retrieve


def default_embedder() -> Callable[[str], Sequence[float]]:
    """The real CLIP/SigLIP text embedder.

    Deliberately not mock-aware. `ML_MODE=mock` uses a fixed 0.45/0.55 blend
    unrelated to the production weighting scheme, so a relevance number produced
    from it is not a smaller version of the real one — it is unrelated to it.
    A benchmark run that silently fell back to mock would emit a full, plausible
    results table that means nothing, so this raises instead.
    """
    from find_api.core.config import settings

    mode = str(getattr(settings, "ML_MODE", "")).lower()
    if mode == "mock":
        raise RuntimeError(
            "ML_MODE=mock cannot produce relevance measurements; the mock "
            "embedder is unrelated to the production weighting scheme. Run the "
            "benchmark against a real model, or use --stub to exercise plumbing."
        )

    from find_api.ml.clip_embedder import get_clip_embedder

    return get_clip_embedder().embed_text
