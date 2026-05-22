"""
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from find_api.core.database import init_db
from find_api.core.recovery import run_analysis_recovery_loop
from find_api.core.storage import init_storage
from find_api.core.config import settings
from find_api.core.model_manager import get_model_manager
from find_api.routers import (
    cluster,
    clusters,
    config,
    gallery,
    people,
    search,
    status,
    upload,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Filter out health check logs
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        return record.getMessage().find("/health") == -1


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("Starting Find API...")

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Initialize MinIO storage
    logger.info("Initializing MinIO storage...")
    init_storage()

    # Start ML model cleanup
    logger.info("Starting ML model cleanup thread...")
    get_model_manager().start_autocleanup(
        ttl_seconds=settings.ML_MODEL_IDLE_TTL_SECONDS,
        process_name="api",
    )

    recovery_task = asyncio.create_task(run_analysis_recovery_loop())

    logger.info("Find API started successfully!")

    try:
        yield
    finally:
        recovery_task.cancel()
        await asyncio.gather(recovery_task, return_exceptions=True)

    logger.info("Shutting down Find API...")


# Create FastAPI app
app = FastAPI(
    title="Find API",
    description="Local-first AI image intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(gallery.router, prefix="/api", tags=["gallery"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(clusters.router, prefix="/api", tags=["clusters"])
app.include_router(cluster.router, prefix="/api", tags=["cluster-ops"])
app.include_router(status.router, prefix="/api", tags=["status"])
app.include_router(config.router, prefix="/api", tags=["config"])
app.include_router(people.router, prefix="/api", tags=["people"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Find API - Local-first AI image intelligence",
        "version": "1.0.0",
        "status": "operational",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
