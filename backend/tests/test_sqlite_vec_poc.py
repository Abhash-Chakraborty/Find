from find_api.core.sqlite_vec_poc import (
    EMBEDDING_DIM,
    SQLiteVecPOC,
)


def test_schema_creation(tmp_path):
    db_file = tmp_path / "sqlite_vec.db"

    poc = SQLiteVecPOC(db_file)
    poc.create_schema()

    assert db_file.exists()


def test_insert_768_dimension_vector(tmp_path):
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


def test_similarity_search(tmp_path):
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


def test_gallery_query_shape(tmp_path):
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
