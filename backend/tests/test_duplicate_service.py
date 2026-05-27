"""Unit tests for near-duplicate detection service."""

from unittest.mock import MagicMock
import pytest

from find_api.services.duplicate_service import (
    SIMILARITY_THRESHOLD,
    find_near_duplicate,
    flag_as_duplicate,
)


def _mock_db(fetchone_return=None):
    db = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = fetchone_return
    db.execute.return_value = result
    return db


class TestFindNearDuplicate:
    def test_returns_none_when_no_neighbours(self):
        db = _mock_db(None)
        assert find_near_duplicate(db, 1, 1, [0.1] * 512) is None

    def test_returns_none_below_threshold(self):
        db = _mock_db((42, 0.95))
        assert find_near_duplicate(db, 1, 1, [0.1] * 512) is None

    def test_returns_id_at_threshold(self):
        db = _mock_db((42, SIMILARITY_THRESHOLD))
        assert find_near_duplicate(db, 1, 1, [0.1] * 512) == 42

    def test_returns_id_above_threshold(self):
        db = _mock_db((99, 0.99))
        assert find_near_duplicate(db, 5, 1, [0.5] * 512) == 99

    def test_excludes_self(self):
        db = _mock_db(None)
        find_near_duplicate(db, 7, 1, [0.1] * 512)
        params = db.execute.call_args[0][1]
        assert params["media_id"] == 7


class TestFlagAsDuplicate:
    def test_commits_after_update(self):
        db = MagicMock()
        flag_as_duplicate(db, 10, 5)
        db.commit.assert_called_once()

    def test_correct_ids_passed(self):
        db = MagicMock()
        flag_as_duplicate(db, 10, 5)
        params = db.execute.call_args[0][1]
        assert params["media_id"] == 10
        assert params["dup_of"] == 5
        
        
class TestDuplicatesEndpoint:
    def test_get_duplicates_returns_200(self):
        """GET /api/duplicates should return 200 with pagination fields."""
        from unittest.mock import MagicMock, patch
        from fastapi.testclient import TestClient
        from find_api.main import app

        mock_rows = []
        mock_total = 0

        with patch("find_api.routers.duplicates.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = mock_rows
            mock_db.execute.return_value.scalar.return_value = mock_total
            mock_get_db.return_value = iter([mock_db])

            client = TestClient(app)
            response = client.get("/api/duplicates")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert "page" in data

    def test_get_duplicates_pagination_params(self):
        """GET /api/duplicates should accept page and limit params."""
        from unittest.mock import MagicMock, patch
        from fastapi.testclient import TestClient
        from find_api.main import app

        with patch("find_api.routers.duplicates.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            mock_db.execute.return_value.scalar.return_value = 0
            mock_get_db.return_value = iter([mock_db])

            client = TestClient(app)
            response = client.get("/api/duplicates?page=2&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["limit"] == 10        