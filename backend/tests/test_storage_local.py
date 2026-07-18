"""Unit tests for LocalStorageBackend (find_api.core.storage_local)."""

from __future__ import annotations

import sys

import pytest

from find_api.core.storage_abstract import StorageException
from find_api.core.storage_local import LocalStorageBackend


@pytest.fixture()
def backend(tmp_path):
    """A LocalStorageBackend rooted at a fresh temp directory."""
    return LocalStorageBackend(str(tmp_path / "storage"))


@pytest.mark.asyncio
async def test_init_storage_creates_base_directory(backend):
    assert not backend.base_path.exists()
    await backend.init_storage()
    assert backend.base_path.is_dir()


@pytest.mark.asyncio
async def test_init_storage_is_idempotent(backend):
    await backend.init_storage()
    await backend.init_storage()
    assert backend.base_path.is_dir()


@pytest.mark.asyncio
async def test_upload_then_get_file_roundtrip(backend):
    await backend.init_storage()
    content = b"hello world"
    returned_name = await backend.upload_file(content, "images/ab/abc.jpg")
    assert returned_name == "images/ab/abc.jpg"
    data = await backend.get_file("images/ab/abc.jpg")
    assert data == content


@pytest.mark.asyncio
async def test_upload_file_creates_nested_directories(backend):
    await backend.init_storage()
    await backend.upload_file(b"data", "a/b/c/d.bin")
    assert (backend.base_path / "a" / "b" / "c" / "d.bin").is_file()


@pytest.mark.asyncio
async def test_get_file_missing_raises_storage_exception(backend):
    await backend.init_storage()
    with pytest.raises(StorageException, match="File not found"):
        await backend.get_file("does/not/exist.jpg")


@pytest.mark.asyncio
async def test_download_file_to_path_copies_content(backend, tmp_path):
    await backend.init_storage()
    content = b"binary-content-1234"
    await backend.upload_file(content, "object.bin")
    destination = tmp_path / "downloaded" / "out.bin"
    await backend.download_file_to_path("object.bin", str(destination))
    assert destination.read_bytes() == content


@pytest.mark.asyncio
async def test_download_file_to_path_missing_raises(backend, tmp_path):
    await backend.init_storage()
    destination = tmp_path / "out.bin"
    with pytest.raises(StorageException, match="File not found"):
        await backend.download_file_to_path("missing.bin", str(destination))


@pytest.mark.asyncio
async def test_get_file_url_returns_files_prefixed_path(backend):
    await backend.init_storage()
    await backend.upload_file(b"x", "images/ab/abc.jpg")
    url = await backend.get_file_url("images/ab/abc.jpg")
    assert url == "/files/images/ab/abc.jpg"


@pytest.mark.asyncio
async def test_get_file_url_missing_raises(backend):
    await backend.init_storage()
    with pytest.raises(StorageException, match="File not found"):
        await backend.get_file_url("missing.jpg")


@pytest.mark.asyncio
async def test_delete_file_removes_existing_file(backend):
    await backend.init_storage()
    await backend.upload_file(b"x", "to-delete.jpg")
    assert await backend.file_exists("to-delete.jpg") is True
    await backend.delete_file("to-delete.jpg")
    assert await backend.file_exists("to-delete.jpg") is False


@pytest.mark.asyncio
async def test_delete_file_missing_file_does_not_raise(backend):
    await backend.init_storage()
    await backend.delete_file("never-existed.jpg")


@pytest.mark.asyncio
async def test_file_exists_true_and_false(backend):
    await backend.init_storage()
    assert await backend.file_exists("nope.jpg") is False
    await backend.upload_file(b"x", "yep.jpg")
    assert await backend.file_exists("yep.jpg") is True


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../secret.txt",
        "../../etc/passwd",
        "images/../../secret.txt",
        "..\\secret.txt",
    ],
)
def test_validate_path_rejects_dot_dot_traversal(backend, malicious_name):
    with pytest.raises(StorageException, match="Path traversal detected"):
        backend._validate_path(malicious_name)


def test_validate_path_normalizes_leading_slash(backend):
    validated = backend._validate_path("/images/abc.jpg")
    assert validated == (backend.base_path / "images" / "abc.jpg").resolve()


def test_validate_path_accepts_clean_relative_path(backend):
    validated = backend._validate_path("images/abc.jpg")
    assert validated.is_relative_to(backend.base_path)


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Windows only test",
)
def test_validate_path_boundary_check_blocks_drive_letter_escape(backend, tmp_path):
    outside = tmp_path / "outside" / "secret.txt"
    with pytest.raises(StorageException, match="outside storage directory"):
        backend._validate_path(str(outside))
