"""
SQLite + sqlite-vec proof of concept.
"""

import sqlite3
import struct

EMBEDDING_DIM = 768


def create_connection(db_path=":memory:"):
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)

    try:
        import sqlite_vec
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "sqlite-vec is required for this desktop-runtime proof of concept. "
            "Install it manually with `pip install sqlite-vec` before running "
            "the sqlite_vec_poc tests."
        ) from exc

    sqlite_vec.load(conn)
    return conn


def create_schema(conn, embedding_dim: int):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """
    )

    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS media_vectors
        USING vec0(
            media_id INTEGER PRIMARY KEY,
            embedding FLOAT[{embedding_dim}]
        )
    """
    )

    conn.commit()


def insert_vector(
    conn,
    media_id: int,
    embedding: list[float],
):
    blob = struct.pack(f"{len(embedding)}f", *embedding)

    conn.execute(
        """
        INSERT INTO media_vectors(media_id, embedding)
        VALUES (?, ?)
        """,
        (media_id, blob),
    )

    conn.commit()


def insert_media(
    conn,
    media_id: int,
    filename: str,
    status: str = "indexed",
):
    conn.execute(
        """
        INSERT INTO media(id, filename, status)
        VALUES (?, ?, ?)
        """,
        (media_id, filename, status),
    )
    conn.commit()


def count_vectors(conn) -> int:
    row = conn.execute("SELECT COUNT(*) FROM media_vectors").fetchone()

    return row[0]


def search_vectors(
    conn,
    query_embedding: list[float],
    limit: int = 10,
):
    blob = struct.pack(
        f"{len(query_embedding)}f",
        *query_embedding,
    )

    rows = conn.execute(
        """
        SELECT
            media_id,
            distance
        FROM media_vectors
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
        """,
        (blob, limit),
    ).fetchall()

    return rows


def search_media(
    conn,
    query_embedding,
    limit=10,
):
    blob = struct.pack(
        f"{len(query_embedding)}f",
        *query_embedding,
    )

    rows = conn.execute(
        """
        SELECT
            m.id,
            m.filename,
            v.distance
        FROM media_vectors v
        JOIN media m
            ON m.id = v.media_id
        WHERE embedding MATCH ?
        AND k = ?
        """,
        (blob, limit),
    ).fetchall()

    return rows


class SQLiteVecPOC:
    def __init__(self, db_path=":memory:"):
        self.conn = create_connection(db_path)

    def create_schema(self):
        create_schema(
            self.conn,
            EMBEDDING_DIM,
        )

    def insert_media(
        self,
        media_id,
        filename,
        embedding,
    ):
        insert_media(
            self.conn,
            media_id,
            filename,
        )

        insert_vector(
            self.conn,
            media_id,
            embedding,
        )

    def search(
        self,
        embedding,
        limit=10,
    ):
        rows = search_media(
            self.conn,
            embedding,
            limit,
        )

        return [
            {
                "id": row[0],
                "filename": row[1],
                "distance": row[2],
            }
            for row in rows
        ]

    def gallery_query(self):
        rows = self.conn.execute(
            """
            SELECT
                id,
                filename,
                status
            FROM media
            ORDER BY id
            """
        ).fetchall()

        return [
            {
                "id": row[0],
                "filename": row[1],
                "status": row[2],
            }
            for row in rows
        ]
