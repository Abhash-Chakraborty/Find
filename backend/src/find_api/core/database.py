"""
Database configuration and session management
"""

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from find_api.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create tables and pgvector extension
    """
    try:
        # Import models to register them
        from find_api.models import cluster, media  # noqa: F401

        # pgvector must exist before SQLAlchemy creates vector columns.
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Create all tables
        Base.metadata.create_all(bind=engine)

        # Normalize schema when using PostgreSQL.
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS liked BOOLEAN DEFAULT false"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS analysis_job_id VARCHAR(64)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR(255)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS thumbnail_content_type VARCHAR(100)"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS thumbnail_size INTEGER"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS thumbnail_width INTEGER"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS thumbnail_height INTEGER"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_media_analysis_job_id "
                        "ON media (analysis_job_id)"
                    )
                )
                conn.execute(text("UPDATE media SET liked = false WHERE liked IS NULL"))
                conn.execute(
                    text(
                        "UPDATE clusters SET centroid_vector = NULL WHERE centroid_vector IS NOT NULL"
                    )
                )
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS clusters "
                        f"ALTER COLUMN centroid_vector TYPE vector({settings.EMBEDDING_DIM})"
                    )
                )

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
