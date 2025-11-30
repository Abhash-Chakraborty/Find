"""
Database configuration and session management
"""

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
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

        # Create pgvector extension when using PostgreSQL
        if engine.dialect.name == "postgresql":
            with engine.connect() as conn:
                # text() required for literal SQL execution in SQLAlchemy 2.0
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(
                    text(
                        "ALTER TABLE IF EXISTS media "
                        "ADD COLUMN IF NOT EXISTS liked BOOLEAN DEFAULT false"
                    )
                )
                conn.execute(text("UPDATE media SET liked = false WHERE liked IS NULL"))
                conn.commit()

        # Create all tables
        Base.metadata.create_all(bind=engine)

        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
