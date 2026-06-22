"""Unit tests for the storage backend factory (find_api.core.storage_factory)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from find_api.core import storage_factory
from find_api.core.config import Settings


@pytest.fixture(autouse=True)
def _reset_global_storage_instance():
    """Ensure the module-level storage singleton doesn't leak across tests."""
    original = storage_factory._storage_instance
    storage_factory._storage_instance = None
    yield
    storage_factory._storage_instance = original


def test_create_storage_backend_selects_minio():
    fake_instance = MagicMock(name="MinIOStorageBackendInstance")
    fake_cls = MagicMock(return_value=fake_instance)

    with patch(
        "find_api.core.storage_minio.MinIOStorageBackend", fake_cls
    ), patch.object(storage_factory, "settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "minio"

        backend = storage_factory.create_storage_backend()

    fake_cls.assert_called_once_with()
    assert backend is fake_instance


def test_create_storage_backend_selects_local():
    fake_instance = MagicMock(name="LocalStorageBackendInstance")
    fake_cls = MagicMock(return_value=fake_instance)

    with patch(
        "find_api.core.storage_local.LocalStorageBackend", fake_cls
    ), patch.object(storage_factory, "settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "local"
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/test_storage"

        backend = storage_factory.create_storage_backend()

    fake_cls.assert_called_once_with("/tmp/test_storage")
    assert backend is fake_instance


def test_create_storage_backend_is_case_insensitive():
    fake_instance = MagicMock(name="LocalStorageBackendInstance")
    fake_cls = MagicMock(return_value=fake_instance)

    with patch(
        "find_api.core.storage_local.LocalStorageBackend", fake_cls
    ), patch.object(storage_factory, "settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "LOCAL"
        mock_settings.LOCAL_STORAGE_PATH = "/tmp/test_storage"

        backend = storage_factory.create_storage_backend()

    fake_cls.assert_called_once_with("/tmp/test_storage")
    assert backend is fake_instance


def test_create_storage_backend_rejects_invalid_value():
    with patch.object(storage_factory, "settings") as mock_settings:
        mock_settings.STORAGE_BACKEND = "s3"

        with pytest.raises(ValueError, match="Invalid STORAGE_BACKEND"):
            storage_factory.create_storage_backend()


def test_storage_neutral_settings_override_minio_compatibility_aliases():
    settings = Settings(
        _env_file=None,
        MINIO_ENDPOINT="legacy:9000",
        MINIO_ACCESS_KEY="legacy-user",
        MINIO_SECRET_KEY="legacy-secret",
        MINIO_BUCKET="legacy-bucket",
        MINIO_SECURE=False,
        MINIO_PUBLIC_ENDPOINT="http://legacy.example/images",
        MINIO_PUBLIC_READ=False,
        STORAGE_ENDPOINT="neutral:9000",
        STORAGE_ACCESS_KEY="neutral-user",
        STORAGE_SECRET_KEY="neutral-secret",
        STORAGE_BUCKET="neutral-bucket",
        STORAGE_SECURE=True,
        STORAGE_PUBLIC_ENDPOINT="https://neutral.example/images",
        STORAGE_PUBLIC_READ=True,
    )

    assert settings.MINIO_ENDPOINT == "neutral:9000"
    assert settings.MINIO_ACCESS_KEY == "neutral-user"
    assert settings.MINIO_SECRET_KEY == "neutral-secret"
    assert settings.MINIO_BUCKET == "neutral-bucket"
    assert settings.MINIO_SECURE is True
    assert settings.MINIO_PUBLIC_ENDPOINT == "https://neutral.example/images"
    assert settings.MINIO_PUBLIC_READ is True


def test_create_storage_backend_defaults_to_minio_when_unset():
    fake_instance = MagicMock(name="MinIOStorageBackendInstance")
    fake_cls = MagicMock(return_value=fake_instance)
    bare_settings = object()

    with patch(
        "find_api.core.storage_minio.MinIOStorageBackend", fake_cls
    ), patch.object(storage_factory, "settings", bare_settings):
        backend = storage_factory.create_storage_backend()

    fake_cls.assert_called_once_with()
    assert backend is fake_instance


@pytest.mark.asyncio
async def test_get_storage_initializes_backend():
    fake_backend = MagicMock()
    fake_backend.init_storage = AsyncMock()

    with patch.object(
        storage_factory, "create_storage_backend", return_value=fake_backend
    ):
        result = await storage_factory.get_storage()

    fake_backend.init_storage.assert_awaited_once()
    assert result is fake_backend


@pytest.mark.asyncio
async def test_initialize_storage_sets_global_instance():
    fake_backend = MagicMock()
    fake_backend.init_storage = AsyncMock()

    with patch.object(
        storage_factory, "create_storage_backend", return_value=fake_backend
    ):
        await storage_factory.initialize_storage()

    assert storage_factory.get_storage_instance() is fake_backend


@pytest.mark.asyncio
async def test_initialize_storage_propagates_failure():
    fake_backend = MagicMock()
    fake_backend.init_storage = AsyncMock(side_effect=RuntimeError("boom"))

    with patch.object(
        storage_factory, "create_storage_backend", return_value=fake_backend
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await storage_factory.initialize_storage()


def test_get_storage_instance_raises_when_not_initialized():
    with pytest.raises(RuntimeError, match="not initialized"):
        storage_factory.get_storage_instance()
