import logging
import os
import sys

from sqlalchemy import create_engine, text

# Add the src-layout package to the path when running this script directly.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from find_api.core.config import settings  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_db():
    logger.info("Starting database migration...")

    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            logger.info("Adding thumbnail metadata columns if missing...")
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR(255);"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS thumbnail_content_type VARCHAR(100);"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS thumbnail_size INTEGER;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS thumbnail_width INTEGER;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE media ADD COLUMN IF NOT EXISTS thumbnail_height INTEGER;"
                )
            )

            # Check current dimension
            logger.info("Clearing existing vectors to allow dimension change...")
            conn.execute(text("UPDATE media SET vector = NULL;"))
            conn.execute(text("UPDATE clusters SET centroid_vector = NULL;"))

            logger.info("Altering media table vector column to 768 dimensions...")
            conn.execute(
                text("ALTER TABLE media ALTER COLUMN vector TYPE vector(768);")
            )
            logger.info("Altering cluster centroid column to 768 dimensions...")
            conn.execute(
                text(
                    "ALTER TABLE clusters ALTER COLUMN centroid_vector TYPE vector(768);"
                )
            )
            conn.commit()
            logger.info("Successfully updated vector column dimension.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate_db()
