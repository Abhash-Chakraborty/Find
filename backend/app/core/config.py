"""
Application configuration using Pydantic settings
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

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
    CLIP_MODEL: str = "ViT-B-32"
    CLIP_PRETRAINED: str = "openai"
    BLIP_MODEL: str = "Salesforce/blip-image-captioning-large"
    YOLO_MODEL: str = "yolov10b.pt"
    USE_GPU: bool = False

    # Processing
    MAX_UPLOAD_SIZE_MB: int = 50
    MAX_BULK_FILES: int = 200
    WORKER_TIMEOUT: int = 600
    BATCH_SIZE: int = 1
    EMBEDDING_DIM: int = 768  # SigLIP ViT-B-16 dimension

    # Clustering
    MIN_CLUSTER_SIZE: int = 2
    MIN_SAMPLES: int = 1

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
