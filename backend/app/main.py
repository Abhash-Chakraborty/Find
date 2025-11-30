"""
Main FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.database import init_db
from app.core.storage import init_storage
from app.routers import upload, gallery, search, clusters, status, cluster

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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

    logger.info("Find API started successfully!")

    yield

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
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
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
