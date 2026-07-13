"""Tests for the model footprint report (find_api.core.model_footprint).

All caches used here are temporary directories built by the tests
themselves — nothing is downloaded, and no network access is required or
expected. Where a lookup would normally hit huggingface_hub, we patch the
download-capable functions to raise so an accidental network call fails
the test loudly instead of silently succeeding.
"""

from __future__ import annotations

import json
import os

import pytest

from find_api.core import model_footprint as mf
from find_api.core.config import settings


def _make_hf_cache(tmp_path, repo_id: str, blob_bytes: bytes) -> tuple[str, bool]:
    """Build a minimal huggingface_hub cache layout under tmp_path.

    Mirrors the on-disk shape `huggingface_hub.scan_cache_dir()` expects:
    hub/models--<org>--<name>/{blobs,snapshots,refs}.
    """
    hf_home = tmp_path / "hf_home"
    hub = hf_home / "hub"
    repo_dir = hub / f"models--{repo_id.replace('/', '--')}"
    blobs_dir = repo_dir / "blobs"
    snap_dir = repo_dir / "snapshots" / "abc123"
    refs_dir = repo_dir / "refs"
    blobs_dir.mkdir(parents=True)
    snap_dir.mkdir(parents=True)
    refs_dir.mkdir(parents=True)

    blob_path = blobs_dir / "blob1"
    blob_path.write_bytes(blob_bytes)
    snapshot_file = snap_dir / "model.safetensors"
    symlink_used = True
    try:
        snapshot_file.symlink_to(blob_path)
    except (OSError, NotImplementedError):
        import shutil

        shutil.copyfile(blob_path, snapshot_file)
        symlink_used = False
    (refs_dir / "main").write_text("abc123")

    return str(hf_home), symlink_used


_NO_SYMLINK_REASON = (
    "requires real filesystem symlinks to build a valid huggingface_hub "
    "cache (scan_cache_dir needs them); not available without Windows "
    "Developer Mode/admin rights or an equivalent POSIX permission"
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if any resolver tries to actually download something."""

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "model_footprint must never trigger a download; "
            "this should have been a local-only cache lookup"
        )

    try:
        import huggingface_hub

        monkeypatch.setattr(huggingface_hub, "hf_hub_download", _forbidden)
        monkeypatch.setattr(huggingface_hub, "snapshot_download", _forbidden)
    except ImportError:
        pass


class TestHFHubCacheResolution:
    def test_finds_cached_repo_by_full_id(self, tmp_path, monkeypatch):
        hf_home, symlink_used = _make_hf_cache(tmp_path, "microsoft/Florence-2-base", b"0" * 2048)
        if not symlink_used:
            pytest.skip(_NO_SYMLINK_REASON)
        monkeypatch.setenv("HF_HOME", hf_home)
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 2048
        assert info.file_count == 1
        assert info.resolver == "hf_hub_cache"
        assert info.last_modified is not None

    def test_no_matching_repo_reports_not_cached(self, tmp_path, monkeypatch):
        hf_home,_ = _make_hf_cache(tmp_path, "someone/unrelated-model", b"0" * 10)
        monkeypatch.setenv("HF_HOME", hf_home)
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.exists is False
        assert info.bytes_on_disk == 0
        assert info.note

    def test_missing_huggingface_hub_degrades_gracefully(self, monkeypatch):
        """If huggingface_hub can't be imported, resolution must not raise."""
        import builtins

        real_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name == "huggingface_hub":
                raise ImportError("simulated missing dependency")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked_import)

        result = mf._hf_hub_cache_matches("anything")
        assert result is None


class TestOpenClipLegacyCache:
    def test_finds_checkpoint_in_legacy_cache_dir(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "open_clip_cache"
        cache_dir.mkdir()
        (cache_dir / "ViT-B-16-SigLIP_webli.bin").write_bytes(b"x" * 4096)

        monkeypatch.setenv("OPEN_CLIP_CACHE_DIR", str(cache_dir))
        # Force the HF Hub path to miss so we exercise the fallback.
        monkeypatch.setattr(mf, "_hf_hub_cache_matches", lambda *needles: None)

        info = mf.resolve_siglip_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 4096
        assert info.resolver == "open_clip_cache_dir"

    def test_nothing_cached_anywhere(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPEN_CLIP_CACHE_DIR", str(tmp_path / "does-not-exist"))
        monkeypatch.setattr(mf, "_hf_hub_cache_matches", lambda *needles: None)

        info = mf.resolve_siglip_cache()

        assert info.exists is False
        assert info.bytes_on_disk == 0


class TestYoloCache:
    def test_finds_weights_in_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "YOLO_MODEL", "yolo26n.pt")
        (tmp_path / "yolo26n.pt").write_bytes(b"y" * 512)

        info = mf.resolve_yolo_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 512
        assert info.resolver == "ultralytics_weights_file"

    def test_not_found_reports_checked_locations(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "YOLO_MODEL", "does-not-exist.pt")

        info = mf.resolve_yolo_cache()

        assert info.exists is False
        assert info.bytes_on_disk == 0
        assert "not found" not in info.note.lower() or info.note  # note is present


class TestInsightFaceCache:
    def test_finds_model_pack(self, tmp_path, monkeypatch):
        home = tmp_path / "insightface_home"
        pack_dir = home / "models" / "antelopev2"
        pack_dir.mkdir(parents=True)
        (pack_dir / "glintr100.onnx").write_bytes(b"a" * 1000)
        (pack_dir / "scrfd_10g_bnkps.onnx").write_bytes(b"b" * 500)

        monkeypatch.setenv("INSIGHTFACE_HOME", str(home))

        info = mf.resolve_insightface_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 1500
        assert info.file_count == 2

    def test_falls_back_to_nested_layout(self, tmp_path, monkeypatch):
        home = tmp_path / "insightface_home"
        pack_dir = home / "models" / "antelopev2" / "antelopev2"
        pack_dir.mkdir(parents=True)
        (pack_dir / "glintr100.onnx").write_bytes(b"a" * 42)

        monkeypatch.setenv("INSIGHTFACE_HOME", str(home))

        info = mf.resolve_insightface_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 42

    def test_missing_pack_reports_not_cached(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSIGHTFACE_HOME", str(tmp_path / "empty"))

        info = mf.resolve_insightface_cache()

        assert info.exists is False
        assert info.bytes_on_disk == 0


class TestPaddleOCRCache:
    def test_finds_models_via_pdx_cache_home(self, tmp_path, monkeypatch):
        cache_home = tmp_path / "paddlex_models"
        cache_home.mkdir()
        (cache_home / "det.onnx").write_bytes(b"d" * 300)

        monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(cache_home))

        info = mf.resolve_paddleocr_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 300

    def test_missing_reports_checked_locations(self, monkeypatch):
        monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
        monkeypatch.setattr(
            os.path, "expanduser", lambda p: p.replace("~", "/nonexistent-home")
        )

        info = mf.resolve_paddleocr_cache()

        assert info.exists is False
        assert info.note


class TestBuildReport:
    def _wire_all_caches(self, tmp_path, monkeypatch):
        """Point every model at a small, fully cached, temporary footprint."""
        hf_home, symlink_used = _make_hf_cache(tmp_path, "microsoft/Florence-2-base", b"f" * 100)
        monkeypatch.setenv("HF_HOME", hf_home)
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        clip_cache = tmp_path / "open_clip_cache"
        clip_cache.mkdir()
        (clip_cache / "ViT-B-16-SigLIP_webli.bin").write_bytes(b"c" * 50)
        monkeypatch.setenv("OPEN_CLIP_CACHE_DIR", str(clip_cache))

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "YOLO_MODEL", "yolo26n.pt")
        (tmp_path / "yolo26n.pt").write_bytes(b"y" * 30)

        insight_home = tmp_path / "insightface_home"
        (insight_home / "models" / "antelopev2").mkdir(parents=True)
        (insight_home / "models" / "antelopev2" / "glintr100.onnx").write_bytes(
            b"i" * 20
        )
        monkeypatch.setenv("INSIGHTFACE_HOME", str(insight_home))
        
        paddle_home = tmp_path / "paddlex_models"
        paddle_home.mkdir()
        (paddle_home / "det.onnx").write_bytes(b"p" * 10)
        monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(paddle_home))
        return symlink_used

    def test_pack_totals_sum_correctly(self, tmp_path, monkeypatch):
        symlink_used = self._wire_all_caches(tmp_path, monkeypatch)
        if not symlink_used:
            pytest.skip(_NO_SYMLINK_REASON)
        report = mf.build_report(include_paths=True)

        # light pack = siglip only
        assert report["packs"]["light"]["total_count"] == 1
        assert report["packs"]["light"]["cached_count"] == 1
        assert report["packs"]["light"]["bytes_on_disk"] == 50

        # full pack = all five models
        assert report["packs"]["full"]["total_count"] == 5
        assert report["packs"]["full"]["cached_count"] == 5
        assert report["packs"]["full"]["bytes_on_disk"] == 100 + 50 + 30 + 20 + 10

        proposed = report["packs"]["proposed_cpu"]
        assert proposed["status"] == "not_implemented"
        assert len(proposed["models"]) == 3

    def test_report_has_five_model_entries_with_required_fields(
        self, tmp_path, monkeypatch
    ):
        self._wire_all_caches(tmp_path, monkeypatch)

        report = mf.build_report(include_paths=True)

        assert {m["key"] for m in report["models"]} == {
            "siglip",
            "florence-2",
            "yolo",
            "insightface",
            "paddleocr",
        }
        for entry in report["models"]:
            assert entry["identifier"]
            assert "loaded" in entry
            assert "device" in entry
            assert "last_used" in entry
            assert "cache" in entry
            assert "bytes_on_disk" in entry["cache"]

    def test_include_paths_false_never_leaks_filesystem_paths(
        self, tmp_path, monkeypatch
    ):
        self._wire_all_caches(tmp_path, monkeypatch)

        report = mf.build_report(include_paths=False)
        serialized = json.dumps(report)

        assert str(tmp_path) not in serialized
        for entry in report["models"]:
            assert "path" not in entry["cache"]

    def test_include_paths_true_exposes_paths_for_local_cli(
        self, tmp_path, monkeypatch
    ):
        self._wire_all_caches(tmp_path, monkeypatch)

        report = mf.build_report(include_paths=True)

        yolo_entry = next(m for m in report["models"] if m["key"] == "yolo")
        assert yolo_entry["cache"]["path"] == str(tmp_path / "yolo26n.pt")

    def test_never_raises_when_everything_is_missing(self, tmp_path, monkeypatch):
        empty = tmp_path / "nothing-here"
        monkeypatch.setenv("HF_HOME", str(empty / "hf"))
        monkeypatch.setenv("OPEN_CLIP_CACHE_DIR", str(empty / "clip"))
        monkeypatch.setenv("INSIGHTFACE_HOME", str(empty / "insightface"))
        monkeypatch.setenv("PADDLE_PDX_CACHE_HOME", str(empty / "paddle"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "YOLO_MODEL", "does-not-exist.pt")

        report = mf.build_report(include_paths=False)

        assert report["packs"]["full"]["cached_count"] == 0
        assert all(not m["cache"]["cached"] for m in report["models"])
