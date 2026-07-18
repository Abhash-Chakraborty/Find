import datetime as dt
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"
SPEC = importlib.util.spec_from_file_location("find_bump_version", SCRIPT)
assert SPEC and SPEC.loader
bump = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bump)


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _release_tree(root: Path, version: str = "1.2.3") -> None:
    _write(root, "backend/pyproject.toml", f'[project]\nversion = "{version}"\n')
    _write(root, "backend/src/find_api/__init__.py", f'__version__ = "{version}"\n')
    _write(root, "frontend/package.json", f'{{\n  "version": "{version}"\n}}\n')
    _write(root, "frontend/src-tauri/Cargo.toml", f'[package]\nversion = "{version}"\n')
    _write(
        root,
        "frontend/src-tauri/tauri.conf.json",
        f'{{\n  "version": "{version}"\n}}\n',
    )
    _write(root, "frontend/src/components/app-shell.tsx", f"<span>v{version}</span>\n")
    _write(
        root,
        "backend/uv.lock",
        f'[[package]]\nname = "find-backend"\nversion = "{version}"\n',
    )
    _write(
        root,
        "frontend/src-tauri/Cargo.lock",
        f'[[package]]\nname = "find-desktop"\nversion = "{version}"\n',
    )
    _write(
        root,
        "CHANGELOG.md",
        "# Changelog\n\ndistributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).\n\n",
    )


def test_semver_bump_levels():
    assert bump.bump_version("1.2.3", "patch") == "1.2.4"
    assert bump.bump_version("1.2.3", "minor") == "1.3.0"
    assert bump.bump_version("1.2.3", "major") == "2.0.0"


def test_updates_every_version_surface_and_changelog(tmp_path):
    _release_tree(tmp_path)

    version = bump.update_versions(
        tmp_path,
        "minor",
        notes=["Ship the canary promotion."],
        release_date=dt.date(2026, 7, 15),
    )

    assert version == "1.3.0"
    assert set(bump.read_versions(tmp_path).values()) == {"1.3.0"}
    assert 'name = "find-backend"\nversion = "1.3.0"' in (
        tmp_path / "backend/uv.lock"
    ).read_text(encoding="utf-8")
    assert 'name = "find-desktop"\nversion = "1.3.0"' in (
        tmp_path / "frontend/src-tauri/Cargo.lock"
    ).read_text(encoding="utf-8")
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [1.3.0] — 2026-07-15" in changelog
    assert "- Ship the canary promotion." in changelog


def test_rejects_inconsistent_versions(tmp_path):
    _release_tree(tmp_path)
    _write(tmp_path, "frontend/package.json", '{\n  "version": "9.9.9"\n}\n')

    try:
        bump.current_version(tmp_path)
    except RuntimeError as exc:
        assert "inconsistent" in str(exc)
    else:
        raise AssertionError("Expected inconsistent version metadata to fail")
