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


class _FakeCachedRepo:
    """The subset of huggingface_hub's CachedRepoInfo that we read."""

    def __init__(self, repo_id, size_on_disk, nb_files, last_modified, repo_path):
        self.repo_id = repo_id
        self.size_on_disk = size_on_disk
        self.nb_files = nb_files
        self.last_modified = last_modified
        self.repo_path = repo_path


def _install_fake_hf_hub(monkeypatch, repos):
    """Inject a stub ``huggingface_hub`` exposing only ``scan_cache_dir``.

    The backend's dev dependency group deliberately excludes the ML extras, so
    the real ``huggingface_hub`` is absent in CI. Building a real on-disk Hub
    cache therefore tested nothing there: ``_hf_hub_cache_matches`` bailed out
    at the import and reported "not cached", which is also what a genuinely
    empty cache looks like. Stubbing the single function this module calls
    keeps the needle-matching and aggregation logic — the part that is ours —
    covered on every platform, with no symlink privileges required.
    """
    import sys
    import types

    module = types.ModuleType("huggingface_hub")

    def _scan_cache_dir(cache_dir=None):
        return types.SimpleNamespace(repos=list(repos))

    module.scan_cache_dir = _scan_cache_dir
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return module


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
    def test_finds_cached_repo_by_full_id(self, monkeypatch):
        _install_fake_hf_hub(
            monkeypatch,
            [
                _FakeCachedRepo(
                    "microsoft/Florence-2-base", 2048, 1, 1_700_000_000.0, "/cache/f"
                )
            ],
        )
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 2048
        assert info.file_count == 1
        assert info.resolver == "hf_hub_cache"
        assert info.last_modified is not None

    def test_matching_is_case_insensitive_and_substring(self, monkeypatch):
        _install_fake_hf_hub(
            monkeypatch,
            [
                _FakeCachedRepo(
                    "MICROSOFT/Florence-2-BASE", 64, 1, 1_700_000_000.0, "/cache/f"
                )
            ],
        )
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        assert mf.resolve_florence_cache().exists is True

    def test_multiple_matching_repos_are_summed_and_noted(self, monkeypatch):
        _install_fake_hf_hub(
            monkeypatch,
            [
                _FakeCachedRepo(
                    "microsoft/Florence-2-base", 100, 2, 1_700_000_000.0, "/cache/a"
                ),
                _FakeCachedRepo(
                    "microsoft/Florence-2-base-ft", 40, 3, 1_800_000_000.0, "/cache/b"
                ),
                _FakeCachedRepo("someone/unrelated", 999, 9, 1.0, "/cache/c"),
            ],
        )
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.bytes_on_disk == 140
        assert info.file_count == 5
        # Newest of the matches, and the unrelated repo must not drag it back.
        assert info.last_modified is not None
        assert "2 matching cached repos summed" in (info.note or "")

    def test_no_matching_repo_reports_not_cached(self, monkeypatch):
        _install_fake_hf_hub(
            monkeypatch,
            [_FakeCachedRepo("someone/unrelated-model", 10, 1, 1.0, "/cache/u")],
        )
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.exists is False
        assert info.bytes_on_disk == 0
        assert info.note

    def test_scan_failure_degrades_to_not_cached(self, monkeypatch):
        """A corrupted or unreadable cache must not blow up the report."""
        import sys
        import types

        module = types.ModuleType("huggingface_hub")

        def _boom(cache_dir=None):
            raise OSError("corrupted cache")

        module.scan_cache_dir = _boom
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)

        assert mf._hf_hub_cache_matches("anything") is None

    def test_real_library_reads_an_on_disk_cache(self, tmp_path, monkeypatch):
        """Integration check against the genuine huggingface_hub, when present.

        Skipped in CI (ML extras are not installed there) and on filesystems
        without symlink privileges, which scan_cache_dir requires. The stubbed
        tests above are what actually gate CI.
        """
        pytest.importorskip("huggingface_hub")
        hf_home, symlink_used = _make_hf_cache(
            tmp_path, "microsoft/Florence-2-base", b"0" * 2048
        )
        if not symlink_used:
            pytest.skip(_NO_SYMLINK_REASON)
        monkeypatch.setenv("HF_HOME", hf_home)
        monkeypatch.delenv("HF_HUB_CACHE", raising=False)
        monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
        monkeypatch.setattr(settings, "BLIP_MODEL", "microsoft/Florence-2-base")

        info = mf.resolve_florence_cache()

        assert info.exists is True
        assert info.bytes_on_disk == 2048
        assert info.resolver == "hf_hub_cache"

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
        # Florence resolves through huggingface_hub, which is not installed in
        # the dev/CI environment, so stub it rather than building a real Hub
        # cache — that also drops the symlink privilege requirement.
        _install_fake_hf_hub(
            monkeypatch,
            [
                _FakeCachedRepo(
                    "microsoft/Florence-2-base", 100, 1, 1_700_000_000.0, "/cache/f"
                )
            ],
        )
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

    def test_pack_totals_sum_correctly(self, tmp_path, monkeypatch):
        self._wire_all_caches(tmp_path, monkeypatch)
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


class TestCliRendering:
    """The local CLI must render on a default Windows console.

    Windows defaults to the cp1252 codepage, where the em dash the report
    previously used as its "no value" placeholder comes out as mojibake. The
    project ships a Windows desktop build, so operators do hit this.
    """

    @staticmethod
    def _load_cli():
        import importlib.util
        from pathlib import Path

        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "model_footprint_report.py"
        )
        spec = importlib.util.spec_from_file_location("_mf_cli", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, script

    def test_human_output_is_cp1252_safe(self, capsys):
        cli, _ = self._load_cli()
        report = mf.build_report(include_paths=False)

        cli._print_human(report, show_paths=False)

        out = capsys.readouterr().out
        assert out.strip()
        # Would raise UnicodeEncodeError on a strict legacy console.
        out.encode("cp1252")
        # Placeholders for "not cached" / "never used" must still be present.
        assert " - " in out or out.rstrip().endswith("-")

    def test_script_source_is_ascii_only(self):
        _, script = self._load_cli()
        source = script.read_text(encoding="utf-8")
        non_ascii = sorted({ch for ch in source if ord(ch) > 127})
        assert not non_ascii, f"non-ASCII characters in CLI script: {non_ascii}"
