#!/usr/bin/env python3
"""
Model footprint report — what each ML model downloads and loads.

Prints, per model: configured identifier, on-disk cache size, loaded/
unloaded state (this process), execution device, and last-use time.
Also prints light/full pack totals and notes the proposed CPU pack is
not implemented yet (see docs/overhaul/inventory/lane-f-ml.md, issue #45).

This is a local admin tool: unlike GET /status/models/footprint, it
prints filesystem cache paths. Run it on the machine whose cache you
want to inspect.

Never downloads model weights — every lookup is a local filesystem read
or a local cache-index read (e.g. huggingface_hub.scan_cache_dir()).

Usage (from the backend directory):
    uv run python scripts/model_footprint_report.py
    uv run python scripts/model_footprint_report.py --json
    uv run python scripts/model_footprint_report.py --no-paths
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _print_human(report: dict, show_paths: bool) -> None:
    print(f"Model footprint report — generated {report['generated_at']}")
    print()

    header = f"{'MODEL':<12} {'PACKS':<12} {'CACHED':<7} {'SIZE':>10}  {'LOADED':<7} {'DEVICE':<22} LAST USED"
    print(header)
    print("-" * len(header))
    for m in report["models"]:
        cache = m["cache"]
        size = _human_bytes(cache["bytes_on_disk"]) if cache["cached"] else "—"
        print(
            f"{m['key']:<12} {','.join(m['packs']):<12} "
            f"{'yes' if cache['cached'] else 'no':<7} {size:>10}  "
            f"{'yes' if m['loaded'] else 'no':<7} {m['device']:<22} "
            f"{m['last_used'] or '—'}"
        )
        print(f"             identifier: {m['identifier']}")
        if cache.get("note"):
            print(f"             note: {cache['note']}")
        if show_paths and cache.get("path"):
            print(f"             path: {cache['path']}")
        for note in m.get("notes", []):
            print(f"             note: {note}")
    print()

    print("Pack totals:")
    for pack_name in ("light", "full"):
        totals = report["packs"][pack_name]
        print(
            f"  {pack_name:<7} {totals['cached_count']}/{totals['total_count']} "
            f"cached, {_human_bytes(totals['bytes_on_disk'])} on disk"
        )
    proposed = report["packs"]["proposed_cpu"]
    print(f"  proposed_cpu  status: {proposed['status']}")
    print(f"                {proposed['note']}")
    for model_label in proposed["models"]:
        print(f"                - {model_label}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="Print JSON instead of a table."
    )
    parser.add_argument(
        "--no-paths",
        action="store_true",
        help="Omit filesystem cache paths (they are included by default "
        "since this script is meant to run locally).",
    )
    args = parser.parse_args()

    # Add src to path so this runs standalone (matches other backend/scripts).
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from find_api.core.model_footprint import build_report

    report = build_report(include_paths=not args.no_paths)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report, show_paths=not args.no_paths)

    return 0


if __name__ == "__main__":
    sys.exit(main())
