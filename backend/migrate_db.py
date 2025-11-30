import os
import sys
from sqlalchemy import create_engine, text
import logging

# Add app to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_db():
    logger.info("Starting database migration...")

    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            # Check current dimension
            logger.info("Clearing existing vectors to allow dimension change...")
            conn.execute(text("UPDATE media SET vector = NULL;"))

            logger.info("Altering media table vector column to 768 dimensions...")
            conn.execute(
                text("ALTER TABLE media ALTER COLUMN vector TYPE vector(768);")
            )
            conn.commit()
            logger.info("✅ Successfully updated vector column dimension.")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate_db()
