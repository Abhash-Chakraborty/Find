import logging
import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from find_api.core.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_vector_dimension(conn: Connection, table: str, column: str) -> int | None:
    row = conn.execute(
        text(
            """
            SELECT atttypmod
            FROM   pg_attribute  a
            JOIN   pg_class      c ON c.oid = a.attrelid
            JOIN   pg_namespace  n ON n.oid = c.relnamespace
            WHERE  n.nspname = current_schema()
            AND    c.relname  = :table
            AND    a.attname  = :column
            AND    a.attnum   > 0
            AND    NOT a.attisdropped
            """
        ),
        {"table": table, "column": column},
    ).fetchone()

    if row is None:
        return None
    atttypmod: int = row[0]
    return atttypmod if atttypmod > 0 else None


def should_clear_vectors(current_dim: int | None, target_dim: int) -> bool:
    if current_dim is None:
        return True
    return current_dim != target_dim


def migrate_db() -> None:
    logger.info("Starting database migration...")

    try:
        engine = create_engine(settings.DATABASE_URL)
        target_dim: int = settings.EMBEDDING_DIM

        with engine.connect() as conn:
            # 1. Thumbnail metadata columns
            logger.info("Adding thumbnail metadata columns if missing...")
            for col_def in (
                "thumbnail_key VARCHAR(255)",
                "thumbnail_content_type VARCHAR(100)",
                "thumbnail_size INTEGER",
                "thumbnail_width INTEGER",
                "thumbnail_height INTEGER",
            ):
                conn.execute(
                    text(f"ALTER TABLE media ADD COLUMN IF NOT EXISTS {col_def};")
                )

            # 2. media.vector
            media_dim = get_vector_dimension(conn, "media", "vector")
            logger.info("media.vector current=%s  target=%d", media_dim, target_dim)

            if should_clear_vectors(media_dim, target_dim):
                logger.warning(
                    "Clearing media.vector (current=%s, target=%d).",
                    media_dim,
                    target_dim,
                )
                conn.execute(text("UPDATE media SET vector = NULL;"))
            else:
                logger.info(
                    "Preserving media.vector (already %d-dimensional).", target_dim
                )

            conn.execute(
                text(
                    f"ALTER TABLE media ALTER COLUMN vector TYPE vector({target_dim});"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS ranking_boost FLOAT NOT NULL DEFAULT 0;"
                )
            )

            # 3. clusters.centroid_vector
            cluster_dim = get_vector_dimension(conn, "clusters", "centroid_vector")
            logger.info(
                "clusters.centroid_vector current=%s  target=%d",
                cluster_dim,
                target_dim,
            )

            if should_clear_vectors(cluster_dim, target_dim):
                logger.warning(
                    "Clearing clusters.centroid_vector (current=%s, target=%d).",
                    cluster_dim,
                    target_dim,
                )
                conn.execute(text("UPDATE clusters SET centroid_vector = NULL;"))
            else:
                logger.info(
                    "Preserving clusters.centroid_vector (already %d-dimensional).",
                    target_dim,
                )

            conn.execute(
                text(
                    f"ALTER TABLE clusters ALTER COLUMN centroid_vector "
                    f"TYPE vector({target_dim});"
                )
            )

            conn.commit()
            logger.info("Schema alterations committed.")

        cfg = Config(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
        )
        command.upgrade(cfg, "head")
        logger.info("Alembic migrations applied.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate_db()
