import importlib.util

import pytest

from find_api.core.sqlite_vec_poc import (
    EMBEDDING_DIM,
    SQLiteVecPOC,
)

SQLITE_VEC_AVAILABLE = importlib.util.find_spec("sqlite_vec") is not None


@pytest.fixture
def sqlite_vec_available():
    if not SQLITE_VEC_AVAILABLE:
        pytest.skip("sqlite-vec is optional and not installed")


def test_missing_sqlite_vec_dependency_message(tmp_path):
    if SQLITE_VEC_AVAILABLE:
        pytest.skip("sqlite-vec is installed")

    db_file = tmp_path / "sqlite_vec.db"

    with pytest.raises(RuntimeError, match="sqlite-vec is required"):
        SQLiteVecPOC(db_file)


def test_schema_creation(tmp_path, sqlite_vec_available):
    db_file = tmp_path / "sqlite_vec.db"

    poc = SQLiteVecPOC(db_file)
    poc.create_schema()

    assert db_file.exists()


def test_insert_768_dimension_vector(tmp_path, sqlite_vec_available):
    db_file = tmp_path / "sqlite_vec.db"

    poc = SQLiteVecPOC(db_file)
    poc.create_schema()

    poc.insert_media(
        media_id=1,
        filename="cat.jpg",
        embedding=[0.1] * EMBEDDING_DIM,
    )

    gallery = poc.gallery_query()

    assert len(gallery) == 1
    assert gallery[0]["filename"] == "cat.jpg"


def test_similarity_search(tmp_path, sqlite_vec_available):
    db_file = tmp_path / "sqlite_vec.db"

    poc = SQLiteVecPOC(db_file)
    poc.create_schema()

    poc.insert_media(
        1,
        "match.jpg",
        [0.1] * EMBEDDING_DIM,
    )

    poc.insert_media(
        2,
        "far.jpg",
        [0.2] * EMBEDDING_DIM,
    )

    results = poc.search(
        [0.1] * EMBEDDING_DIM,
        limit=2,
    )

    assert len(results) == 2
    assert results[0]["id"] == 1


def test_gallery_query_shape(tmp_path, sqlite_vec_available):
    db_file = tmp_path / "sqlite_vec.db"

    poc = SQLiteVecPOC(db_file)
    poc.create_schema()

    poc.insert_media(
        1,
        "image.jpg",
        [0.1] * EMBEDDING_DIM,
    )

    gallery = poc.gallery_query()

    assert gallery == [
        {
            "id": 1,
            "filename": "image.jpg",
            "status": "indexed",
        }
    ]
