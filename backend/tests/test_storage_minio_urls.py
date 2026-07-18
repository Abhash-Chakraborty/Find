"""Regression tests for public MinIO URL rewriting."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from find_api.core.config import settings
from find_api.core.storage_minio import MinIOStorageBackend


def test_presigned_url_does_not_repeat_public_endpoint_prefix(monkeypatch):
    monkeypatch.setattr(
        settings, "MINIO_PUBLIC_ENDPOINT", "http://localhost:9200/images"
    )
    monkeypatch.setattr(settings, "MINIO_PUBLIC_READ", False)

    with patch("find_api.core.storage_minio.Minio") as minio_cls:
        minio_cls.return_value.presigned_get_object.return_value = (
            "http://localhost:9200/images/images/example.webp?signature=test"
        )
        backend = MinIOStorageBackend()
        backend._public_client = minio_cls.return_value

        url = asyncio.run(backend.get_file_url("images/example.webp"))

    assert url == "http://localhost:9200/images/images/example.webp?signature=test"
