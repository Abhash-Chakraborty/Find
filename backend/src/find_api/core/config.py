"""
Application configuration using Pydantic settings
"""

import os
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

    # Queue mode — "redis" for Docker/RQ, "sqlite" for desktop mode
    QUEUE_MODE: Literal["redis", "sqlite"] = "redis"
    QUEUE_DB_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "queue.db",
    )

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

    # Storage
    STORAGE_BACKEND: Literal["minio", "local"] = "minio"
    LOCAL_STORAGE_PATH: str = "./storage/uploads"
    STORAGE_ENDPOINT: Optional[str] = None
    STORAGE_ACCESS_KEY: Optional[str] = None
    STORAGE_SECRET_KEY: Optional[str] = None
    STORAGE_BUCKET: Optional[str] = None
    STORAGE_SECURE: Optional[bool] = None
    STORAGE_PUBLIC_ENDPOINT: Optional[str] = None
    STORAGE_PUBLIC_READ: Optional[bool] = None
    STORAGE_AUTO_CREATE_BUCKET: bool = True

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

    @model_validator(mode="after")
    def apply_storage_aliases(self):
        """Prefer neutral STORAGE_* values while preserving MINIO_* compatibility."""
        if self.STORAGE_ENDPOINT:
            self.MINIO_ENDPOINT = self.STORAGE_ENDPOINT
        if self.STORAGE_ACCESS_KEY:
            self.MINIO_ACCESS_KEY = self.STORAGE_ACCESS_KEY
        if self.STORAGE_SECRET_KEY:
            self.MINIO_SECRET_KEY = self.STORAGE_SECRET_KEY
        if self.STORAGE_BUCKET:
            self.MINIO_BUCKET = self.STORAGE_BUCKET
        if self.STORAGE_SECURE is not None:
            self.MINIO_SECURE = self.STORAGE_SECURE
        if self.STORAGE_PUBLIC_ENDPOINT:
            self.MINIO_PUBLIC_ENDPOINT = self.STORAGE_PUBLIC_ENDPOINT
        if self.STORAGE_PUBLIC_READ is not None:
            self.MINIO_PUBLIC_READ = self.STORAGE_PUBLIC_READ

        return self

    @model_validator(mode="after")
    def reject_default_secrets_in_production(self):
        """Fail closed when known-default credentials are used in production.

        These defaults are convenient for local development but are publicly
        known, so a production deployment that forgets to override them would
        ship with guessable database/object-store credentials.

        Runs after :meth:`apply_storage_aliases` so it checks the effective
        credentials (STORAGE_* values already copied onto MINIO_*).
        """
        if self.ENVIRONMENT.lower() != "production":
            return self

        insecure: list[str] = []
        if "find123" in self.DATABASE_URL:
            insecure.append("DATABASE_URL (default password)")
        if self.MINIO_ACCESS_KEY == "minioadmin":
            insecure.append("MINIO_ACCESS_KEY/STORAGE_ACCESS_KEY")
        if self.MINIO_SECRET_KEY == "minioadmin":
            insecure.append("MINIO_SECRET_KEY/STORAGE_SECRET_KEY")

        if insecure:
            raise ValueError(
                "Refusing to start in production with default credentials: "
                + ", ".join(insecure)
                + ". Set strong, unique values for these via environment variables."
            )
        return self


settings = Settings()
