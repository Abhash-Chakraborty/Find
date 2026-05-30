"""Tests for GET /api/search response shape and pagination behavior."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from find_api.core.database import get_db
from find_api.main import app


def _mock_search(client, fake_rows, *, params=None, total_count=None, return_db=False):
    """Call /api/search with mocked embeddings and paginated DB responses."""
    mock_embedder = MagicMock()
    mock_embedder.embed_text.return_value = [0.0] * 768

    mock_db = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = (
        len(fake_rows) if total_count is None else total_count
    )
    mock_db.execute.side_effect = [count_result, iter(fake_rows)]

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
            response = client.get(
                "/api/search", params={"q": "sunset", **(params or {})}
            )
            if return_db:
                return response, mock_db
            return response
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestSearchResponseShape:
    """Search response shape with mocked data."""

    def test_search_result_shape(self, client):
        fake_row = MagicMock(
            id=1,
            filename="beach.jpg",
            minio_key="images/ab/abc.jpg",
            thumbnail_key="thumbnails/ab/abc.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=512,
            thumbnail_width=256,
            thumbnail_height=144,
            status="indexed",
            liked=False,
            width=1920,
            height=1080,
            cluster_id=None,
            similarity=0.82,
            metadata_json='{"caption": "a beach", "objects": ["sand"]}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

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

    def test_ocr_text_boost_reranks_results(self, client):
        text_heavy = MagicMock(
            id=201,
            filename="calendar.png",
            minio_key="images/20/201.png",
            thumbnail_key="thumbnails/20/201.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=256,
            thumbnail_width=128,
            thumbnail_height=72,
            status="indexed",
            liked=False,
            width=1200,
            height=800,
            cluster_id=None,
            similarity=0.62,
            metadata_json='{"caption": "desk calendar", "objects": [], "ocr_text": "weekly planning calendar monday tuesday"}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        portrait = MagicMock(
            id=202,
            filename="portrait.jpg",
            minio_key="images/20/202.jpg",
            thumbnail_key="thumbnails/20/202.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=256,
            thumbnail_width=128,
            thumbnail_height=72,
            status="indexed",
            liked=False,
            width=1200,
            height=800,
            cluster_id=None,
            similarity=0.64,
            metadata_json='{"caption": "person portrait", "objects": ["person"], "ocr_text": ""}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        response = _mock_search(
            client, [portrait, text_heavy], params={"q": "calendar text"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["results"][0]["media_id"] == 201

    def test_similarity_is_bounded_to_one(self, client):
        row = MagicMock(
            id=301,
            filename="notes.png",
            minio_key="images/30/301.png",
            thumbnail_key="thumbnails/30/301.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=256,
            thumbnail_width=128,
            thumbnail_height=72,
            status="indexed",
            liked=False,
            width=1200,
            height=800,
            cluster_id=None,
            similarity=0.99,
            metadata_json='{"caption": "calendar notes", "objects": [], "ocr_text": "calendar notes monday"}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        response = _mock_search(client, [row], params={"q": "calendar notes text"})

        assert response.status_code == 200
        body = response.json()
        assert body["results"][0]["similarity"] <= 1.0

    def test_ocr_not_returned_by_default_and_included_when_requested(self, client):
        row = MagicMock(
            id=302,
            filename="receipt.png",
            minio_key="images/30/302.png",
            thumbnail_key="thumbnails/30/302.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=256,
            thumbnail_width=128,
            thumbnail_height=72,
            status="indexed",
            liked=False,
            width=1200,
            height=800,
            cluster_id=None,
            similarity=0.61,
            metadata_json='{"caption": "receipt", "objects": [], "ocr_text": "total 42.00"}',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        default_response = _mock_search(client, [row], params={"q": "receipt"})
        include_response = _mock_search(
            client,
            [row],
            params={"q": "receipt", "include_ocr": "true"},
        )

        assert default_response.status_code == 200
        assert include_response.status_code == 200

        default_meta = default_response.json()["results"][0]["metadata"]
        include_meta = include_response.json()["results"][0]["metadata"]
        assert "ocr_text" not in default_meta
        assert include_meta["ocr_text"] == "total 42.00"

    def test_hidden_filter_is_applied_in_search_queries(self, client):
        row = MagicMock(
            id=400,
            filename="visible.png",
            minio_key="images/40/400.png",
            thumbnail_key="thumbnails/40/400.webp",
            thumbnail_content_type="image/webp",
            thumbnail_size=256,
            thumbnail_width=128,
            thumbnail_height=72,
            status="indexed",
            liked=False,
            width=100,
            height=100,
            cluster_id=None,
            similarity=0.7,
            metadata_json="{}",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        response, mock_db = _mock_search(client, [row], return_db=True)

        assert response.status_code == 200
        assert mock_db.execute.call_count == 2
        count_sql = str(mock_db.execute.call_args_list[0].args[0])
        result_sql = str(mock_db.execute.call_args_list[1].args[0])
        assert "is_hidden = false" in count_sql
        assert "is_hidden = false" in result_sql
