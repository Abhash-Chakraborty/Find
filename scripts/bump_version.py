#!/usr/bin/env python3
"""Keep Find's backend, web, desktop, UI, lock, and changelog versions aligned."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from pathlib import Path

VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def bump_version(current: str, level: str) -> str:
    major, minor, patch = parse_version(current)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump level: {level}")


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one version match in {path}, found {count}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def read_versions(root: Path) -> dict[str, str]:
    files = {
        "backend": (root / "backend/pyproject.toml", r'^version = "([^"]+)"'),
        "api": (root / "backend/src/find_api/__init__.py", r'^__version__ = "([^"]+)"'),
        "web": (root / "frontend/package.json", r'^  "version": "([^"]+)"'),
        "desktop": (root / "frontend/src-tauri/Cargo.toml", r'^version = "([^"]+)"'),
        "tauri": (
            root / "frontend/src-tauri/tauri.conf.json",
            r'^  "version": "([^"]+)"',
        ),
        "ui": (root / "frontend/src/components/app-shell.tsx", r">v(\d+\.\d+\.\d+)<"),
    }
    versions: dict[str, str] = {}
    for name, (path, pattern) in files.items():
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            raise RuntimeError(f"Version not found in {path}")
        versions[name] = match.group(1)
    return versions


def current_version(root: Path) -> str:
    versions = read_versions(root)
    unique = set(versions.values())
    if len(unique) != 1:
        rendered = ", ".join(f"{name}={version}" for name, version in versions.items())
        raise RuntimeError(f"Version metadata is inconsistent: {rendered}")
    version = unique.pop()
    parse_version(version)
    return version


def update_versions(
    root: Path,
    level: str,
    *,
    notes: list[str] | None = None,
    release_date: dt.date | None = None,
) -> str:
    old = current_version(root)
    new = bump_version(old, level)

    replacements = [
        (root / "backend/pyproject.toml", r'^version = "[^"]+"', f'version = "{new}"'),
        (
            root / "backend/src/find_api/__init__.py",
            r'^__version__ = "[^"]+"',
            f'__version__ = "{new}"',
        ),
        (
            root / "frontend/package.json",
            r'^  "version": "[^"]+"',
            f'  "version": "{new}"',
        ),
        (
            root / "frontend/src-tauri/Cargo.toml",
            r'^version = "[^"]+"',
            f'version = "{new}"',
        ),
        (
            root / "frontend/src-tauri/tauri.conf.json",
            r'^  "version": "[^"]+"',
            f'  "version": "{new}"',
        ),
        (
            root / "frontend/src/components/app-shell.tsx",
            r">v\d+\.\d+\.\d+<",
            f">v{new}<",
        ),
        (
            root / "backend/uv.lock",
            r'(\[\[package\]\]\nname = "find-backend"\nversion = ")[^"]+("\n)',
            rf"\g<1>{new}\2",
        ),
        (
            root / "frontend/src-tauri/Cargo.lock",
            r'(\[\[package\]\]\nname = "find-desktop"\nversion = ")[^"]+("\n)',
            rf"\g<1>{new}\2",
        ),
    ]
    for path, pattern, replacement in replacements:
        _replace_once(path, pattern, replacement)

    changelog = root / "CHANGELOG.md"
    content = changelog.read_text(encoding="utf-8")
    release_date = release_date or dt.date.today()
    note_lines = notes or ["Release notes will be finalized during maintainer review."]
    bullets = "\n".join(
        line if line.lstrip().startswith("-") else f"- {line}"
        for line in note_lines
        if line.strip()
    )
    section = f"## [{new}] — {release_date.isoformat()}\n\n### Changed\n\n{bullets}\n\n"
    marker = "distributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).\n\n"
    if marker not in content:
        raise RuntimeError("Changelog insertion marker not found")
    changelog.write_text(
        content.replace(marker, marker + section, 1), encoding="utf-8", newline="\n"
    )

    if current_version(root) != new:
        raise RuntimeError("Version update did not converge")
    return new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("level", nargs="?", choices=("patch", "minor", "major"))
    parser.add_argument(
        "--check", action="store_true", help="Only validate version consistency"
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--notes-file", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    if args.check:
        version = current_version(root)
    else:
        if not args.level:
            parser.error("level is required unless --check is used")
        notes = None
        if args.notes_file and args.notes_file.exists():
            notes = [
                line.strip()
                for line in args.notes_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        version = update_versions(root, args.level, notes=notes)

    print(version)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
