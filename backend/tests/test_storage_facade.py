"""Tests for the synchronous app-level storage facade."""

from __future__ import annotations

import pytest

from find_api.core import storage


class FakeAsyncStorageBackend:
    """Minimal async backend used to verify sync facade compatibility."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "image/jpeg",
    ) -> str:
        assert file_data
        assert content_type
        return object_name

    async def get_file(self, object_name: str) -> bytes:
        return f"data:{object_name}".encode()

    async def download_file_to_path(
        self, object_name: str, destination_path: str
    ) -> None:
        assert object_name
        assert destination_path

    async def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        assert expires > 0
        return f"/files/{object_name}"

    async def delete_file(self, object_name: str) -> None:
        self.deleted.append(object_name)

    async def file_exists(self, object_name: str) -> bool:
        return object_name == "present.jpg"


@pytest.fixture()
def fake_backend(monkeypatch):
    backend = FakeAsyncStorageBackend()
    monkeypatch.setattr(storage, "get_storage_instance", lambda: backend)
    return backend


def test_storage_facade_initializes_backend_inside_worker_process(monkeypatch):
    """The first worker call initializes storage when app lifespan never ran."""
    backend = FakeAsyncStorageBackend()
    initialized = False

    def get_instance():
        if not initialized:
            raise storage.StorageNotInitializedError(
                "Storage backend not initialized. Call initialize_storage() first."
            )
        return backend

    def initialize():
        nonlocal initialized
        initialized = True

    monkeypatch.setattr(storage, "get_storage_instance", get_instance)
    monkeypatch.setattr(storage, "init_storage", initialize)

    assert storage.get_file("worker-image.jpg") == b"data:worker-image.jpg"
    assert initialized is True


@pytest.mark.asyncio
async def test_sync_storage_facade_returns_values_inside_running_event_loop(
    fake_backend,
):
    """Async routes can still call the existing synchronous storage helpers."""
    assert storage.upload_file(b"x", "image.jpg") == "image.jpg"
    assert storage.get_file("image.jpg") == b"data:image.jpg"
    assert storage.get_file_url("image.jpg") == "/files/image.jpg"
    assert storage.file_exists("present.jpg") is True

    storage.delete_file("image.jpg")
    assert fake_backend.deleted == ["image.jpg"]
