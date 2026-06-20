"""
Application configuration using Pydantic settings
"""

from typing import Literal, Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    # API
    ENVIRONMENT: Literal["local", "development", "staging", "production"] = "local"
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
    ML_MODE: Literal["full", "mock", "remote"] = "full"
    REMOTE_ML_URL: Optional[str] = None
    REMOTE_ML_API_KEY: Optional[str] = None
    REMOTE_ML_STRIP_EXIF: bool = True
    REMOTE_ML_FEATURES: str = "embed,caption,detect,ocr,cluster"
    ML_MODEL_IDLE_TTL_SECONDS: int = 300
    ML_MAX_LOADED_MODELS: int = 5
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

    # Auth (small-team instance sharing)
    SESSION_TTL_HOURS: int = 24
    INVITE_TTL_HOURS: int = 48

    @field_validator(
        "ML_MODEL_IDLE_TTL_SECONDS",
        "ML_MAX_LOADED_MODELS",
        "SESSION_TTL_HOURS",
        "INVITE_TTL_HOURS",
    )
    @classmethod
    def validate_positive_int(cls, value: int, info):
        """Keep memory lifecycle settings positive so cleanup cannot be disabled accidentally."""
        if value <= 0:
            raise ValueError(f"{info.field_name} must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_remote_ml_config(self):
        """Require remote ML settings when remote mode is enabled."""
        if self.ML_MODE.lower() != "remote":
            return self

        if not self.REMOTE_ML_URL or not self.REMOTE_ML_URL.strip():
            raise ValueError(
                "ML_MODE=remote requires REMOTE_ML_URL. "
                "Set REMOTE_ML_URL to a reachable self-hosted Find ML server "
                "or change ML_MODE to full or mock."
            )

        if not self.REMOTE_ML_API_KEY or not self.REMOTE_ML_API_KEY.strip():
            raise ValueError(
                "ML_MODE=remote requires REMOTE_ML_API_KEY. "
                "Set REMOTE_ML_API_KEY to a bearer token shared with your remote ML server "
                "or change ML_MODE to full or mock."
            )

        return self


settings = Settings()
