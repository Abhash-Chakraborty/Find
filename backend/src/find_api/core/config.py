"""
Application configuration using Pydantic settings
"""

from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql://find:find123@localhost:5432/find"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "images"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_ENDPOINT: Optional[str] = None
    MINIO_PUBLIC_READ: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # ML Models
    ML_MODE: Literal["full", "mock"] = "full"
    CLIP_MODEL: str = "ViT-B-16-SigLIP"
    CLIP_PRETRAINED: str = "webli"
    BLIP_MODEL: str = "microsoft/Florence-2-base"
    YOLO_MODEL: str = "yolo26n.pt"
    USE_GPU: bool = False
    YOLO_HALF: bool = True

    # Processing
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_BULK_FILES: int = 200
    MAX_BULK_TOTAL_SIZE_MB: int = 500
    MAX_BULK_COMPRESSION_RATIO: int = 100
    WORKER_TIMEOUT: int = 600
    BATCH_SIZE: int = 1
    EMBEDDING_DIM: int = 768  # SigLIP ViT-B-16 dimension

    # Clustering
    MIN_CLUSTER_SIZE: int = 2
    MIN_SAMPLES: int = 1
    CLUSTERING_N_JOBS: int = -1
    CLUSTERING_BACKEND: str = "auto"


settings = Settings()
