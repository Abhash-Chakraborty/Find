"""Tests for GET /api/search response shape and pagination behavior."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from find_api.core.database import get_db
from find_api.main import app
from find_api.services.query_cache import clear_query_cache, invalidate_query_cache


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    clear_query_cache()


def _fake_search_row(media_id: int = 1, similarity: float = 0.82) -> MagicMock:
    return MagicMock(
        id=media_id,
        filename=f"photo-{media_id}.jpg",
        minio_key=f"images/{media_id}/photo.jpg",
        thumbnail_key=f"thumbnails/{media_id}/photo.webp",
        thumbnail_content_type="image/webp",
        thumbnail_size=512,
        thumbnail_width=256,
        thumbnail_height=144,
        status="indexed",
        liked=False,
        width=1920,
        height=1080,
        cluster_id=None,
        similarity=similarity,
        metadata_json='{"caption": "a beach", "objects": ["sand"]}',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _signature_result(token: str = "1:2026-01-01T00:00:00+00:00") -> MagicMock:
    result = MagicMock()
    indexed_count, max_processed_at = token.split(":", 1)
    result.mappings.return_value.first.return_value = {
        "indexed_count": int(indexed_count),
        "max_processed_at": max_processed_at,
    }
    return result


def _mock_search(client, fake_rows, *, params=None, total_count=None):
    """Call /api/search with mocked embeddings and paginated DB responses."""
    mock_embedder = MagicMock()
    mock_embedder.embed_text.return_value = [0.0] * 768

    mock_db = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = (
        len(fake_rows) if total_count is None else total_count
    )
    mock_db.execute.side_effect = [_signature_result(), count_result, iter(fake_rows)]

    def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override

    try:
        with (
            patch(
                "find_api.routers.search.settings",
                ML_MODE="mock",
                EMBEDDING_DIM=768,
            ),
            patch(
                "find_api.ml.mock_embedder.get_mock_embedder",
                return_value=mock_embedder,
            ),
        ):
            return client.get("/api/search", params={"q": "sunset", **(params or {})})
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestSearchResponseShape:
    """Search response shape with mocked data."""

    def test_search_result_shape(self, client):
        fake_row = _fake_search_row()

        response = _mock_search(client, [fake_row])

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "sunset"
        assert body["total"] == 1
        assert body["page"] == 1
        assert body["limit"] == 24
        assert body["skip"] == 0
        assert body["has_more"] is False
        assert "results" in body

        result = body["results"][0]
        assert "media_id" in result
        assert "similarity" in result
        assert isinstance(result["similarity"], float)

        meta = result["metadata"]
        expected = {
            "id",
            "filename",
            "minio_key",
            "thumbnail_key",
            "thumbnail_content_type",
            "thumbnail_size",
            "thumbnail_width",
            "thumbnail_height",
            "thumbnail_url",
            "status",
            "liked",
            "width",
            "height",
            "cluster_id",
            "created_at",
            "caption",
            "objects",
            "url",
            "thumbnail_url",
        }
        assert expected.issubset(meta.keys())
        assert meta["thumbnail_url"] == "/api/image/1/thumbnail"

    def test_empty_results(self, client):
        response = _mock_search(client, [])

        assert response.status_code == 200
        body = response.json()
        assert body["results"] == []
        assert body["total"] == 0
        assert body["has_more"] is False

    def test_search_pagination_metadata(self, client):
        fake_rows = [
            MagicMock(
                id=101,
                filename="photo-101.jpg",
                minio_key="images/10/101.jpg",
                thumbnail_key="thumbnails/10/101.webp",
                thumbnail_content_type="image/webp",
                thumbnail_size=256,
                thumbnail_width=128,
                thumbnail_height=72,
                status="indexed",
                liked=False,
                width=1920,
                height=1080,
                cluster_id=None,
                similarity=0.8,
                metadata_json="{}",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            MagicMock(
                id=102,
                filename="photo-102.jpg",
                minio_key="images/10/102.jpg",
                thumbnail_key="thumbnails/10/102.webp",
                thumbnail_content_type="image/webp",
                thumbnail_size=256,
                thumbnail_width=128,
                thumbnail_height=72,
                status="indexed",
                liked=False,
                width=1920,
                height=1080,
                cluster_id=None,
                similarity=0.79,
                metadata_json="{}",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        ]

        response = _mock_search(
            client,
            fake_rows,
            params={"limit": 2, "skip": 2},
            total_count=5,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert body["limit"] == 2
        assert body["skip"] == 2
        assert body["page"] == 2
        assert body["has_more"] is True
        assert [row["media_id"] for row in body["results"]] == [101, 102]

    def test_missing_query_returns_422(self, client):
        response = client.get("/api/search")
        assert response.status_code == 422


class TestSearchDiagnostics:
    """Tests for the debug diagnostics response behavior."""

    def _mock_search_with_debug(self, client, fake_rows, debug: bool, environment: str):
        """Call /api/search with debug param and a controlled environment."""
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.0] * 768

        mock_db = MagicMock()
        count_result = MagicMock()
        count_result.scalar.return_value = len(fake_rows)
        side_effects = [count_result, iter(fake_rows)]
        if not debug:
            side_effects.insert(0, _signature_result())
        mock_db.execute.side_effect = side_effects

        def _override():
            yield mock_db

        app.dependency_overrides[get_db] = _override

        try:
            with (
                patch(
                    "find_api.routers.search.settings",
                    ML_MODE="mock",
                    EMBEDDING_DIM=768,
                    ENVIRONMENT=environment,
                ),
                patch(
                    "find_api.ml.mock_embedder.get_mock_embedder",
                    return_value=mock_embedder,
                ),
            ):
                return client.get(
                    "/api/search", params={"q": "sunset", "debug": str(debug).lower()}
                )
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_diagnostics_present_when_debug_true_local(self, client):
        """diagnostics block is returned when debug=True in local environment."""
        response = self._mock_search_with_debug(
            client, [], debug=True, environment="local"
        )

        assert response.status_code == 200
        body = response.json()
        assert "diagnostics" in body
        diag = body["diagnostics"]
        assert "embedding_ms" in diag
        assert "retrieval_ms" in diag
        assert "total_ms" in diag
        assert "results_returned" in diag
        assert "similarity_threshold" in diag
        assert "ml_mode" in diag
        assert isinstance(diag["embedding_ms"], float)
        assert isinstance(diag["retrieval_ms"], float)
        assert isinstance(diag["total_ms"], float)
        assert isinstance(diag["results_returned"], int)

    def test_diagnostics_present_when_debug_true_development(self, client):
        """diagnostics block is returned when debug=True in development environment."""
        response = self._mock_search_with_debug(
            client, [], debug=True, environment="development"
        )

        assert response.status_code == 200
        assert "diagnostics" in response.json()

    def test_diagnostics_absent_when_debug_false(self, client):
        """diagnostics block is NOT returned when debug=False."""
        response = self._mock_search_with_debug(
            client, [], debug=False, environment="local"
        )

        assert response.status_code == 200
        assert "diagnostics" not in response.json()

    def test_diagnostics_absent_in_production(self, client):
        """diagnostics block is NOT returned in production even if debug=True."""
        response = self._mock_search_with_debug(
            client, [], debug=True, environment="production"
        )

        assert response.status_code == 200
        assert "diagnostics" not in response.json()

    def test_diagnostics_absent_in_staging(self, client):
        """diagnostics block is NOT returned in staging even if debug=True."""
        response = self._mock_search_with_debug(
            client, [], debug=True, environment="staging"
        )

        assert response.status_code == 200
        assert "diagnostics" not in response.json()


class TestSearchQueryCache:
    """Search query cache behavior."""

    def _mock_cached_search(self, client, request_rows, signatures=None):
        mock_embedder = MagicMock()
        mock_embedder.embed_text.return_value = [0.0] * 768

        mock_db = MagicMock()
        side_effects = []
        signatures = signatures or ["1:2026-01-01T00:00:00+00:00"] * len(request_rows)
        for rows, signature in zip(request_rows, signatures):
            side_effects.append(_signature_result(signature))
            if rows is None:
                continue
            count_result = MagicMock()
            count_result.scalar.return_value = len(rows)
            side_effects.extend([count_result, iter(rows)])
        mock_db.execute.side_effect = side_effects

        def _override():
            yield mock_db

        app.dependency_overrides[get_db] = _override

        patches = (
            patch(
                "find_api.routers.search.settings",
                ML_MODE="mock",
                EMBEDDING_DIM=768,
                ENVIRONMENT="local",
            ),
            patch(
                "find_api.ml.mock_embedder.get_mock_embedder",
                return_value=mock_embedder,
            ),
        )
        return mock_db, mock_embedder, patches

    def test_repeated_query_reuses_cached_response(self, client):
        row = _fake_search_row(media_id=11)
        mock_db, mock_embedder, patches = self._mock_cached_search(
            client, [[row], None]
        )

        try:
            with patches[0], patches[1]:
                first = client.get("/api/search", params={"q": "  Sunset   Beach  "})
                second = client.get("/api/search", params={"q": "sunset beach"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        mock_embedder.embed_text.assert_called_once_with("  Sunset   Beach  ")
        assert mock_db.execute.call_count == 4

    def test_pagination_change_misses_cache(self, client):
        mock_db, mock_embedder, patches = self._mock_cached_search(
            client,
            [[_fake_search_row(media_id=21)], [_fake_search_row(media_id=22)]],
        )

        try:
            with patches[0], patches[1]:
                first = client.get("/api/search", params={"q": "sunset", "skip": 0})
                second = client.get("/api/search", params={"q": "sunset", "skip": 1})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_embedder.embed_text.call_count == 2
        assert mock_db.execute.call_count == 6

    def test_invalidated_cache_forces_recompute(self, client):
        mock_db, mock_embedder, patches = self._mock_cached_search(
            client,
            [[_fake_search_row(media_id=31)], [_fake_search_row(media_id=32)]],
        )

        try:
            with patches[0], patches[1]:
                first = client.get("/api/search", params={"q": "sunset"})
                invalidate_query_cache()
                second = client.get("/api/search", params={"q": "sunset"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_embedder.embed_text.call_count == 2
        assert mock_db.execute.call_count == 6

    def test_index_signature_change_misses_cache(self, client):
        mock_db, mock_embedder, patches = self._mock_cached_search(
            client,
            [[_fake_search_row(media_id=41)], [_fake_search_row(media_id=42)]],
            signatures=[
                "1:2026-01-01T00:00:00+00:00",
                "2:2026-01-02T00:00:00+00:00",
            ],
        )

        try:
            with patches[0], patches[1]:
                first = client.get("/api/search", params={"q": "sunset"})
                second = client.get("/api/search", params={"q": "sunset"})
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert first.status_code == 200
        assert second.status_code == 200
        assert mock_embedder.embed_text.call_count == 2
        assert mock_db.execute.call_count == 6
