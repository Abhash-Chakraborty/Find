#!/usr/bin/env python3
"""
CPU runtime profile measurement - what the CPU-only pack costs to run.

Issue #339 asks for image size, idle RAM, peak RAM, and per-image latency
recorded on a CPU-only machine. This produces the last three by loading each ML
stage in turn and running it over a fixed set of images, sampling process RSS
throughout. Image size comes from `docker image inspect` and is recorded in
docs/guides/cpu-runtime-profile.md rather than here.

Stages are measured in a deliberate order - cheapest to load first - and each
stage reports RSS *delta* over the previous steady state, so the numbers add up
to the peak rather than each claiming the whole process. Loading every model in
one process is also the honest arrangement: that is what a Find worker does.

Everything is local. No image, caption, OCR text, embedding, or measurement
leaves the machine. Model weights are fetched from their normal upstream caches
on first run exactly as the worker would fetch them, so the first run of each
stage includes download time and is reported separately from steady state.

Usage (from the backend directory, inside a CPU-profile container):

    uv run python scripts/cpu_profile_report.py --images 10
    uv run python scripts/cpu_profile_report.py --json --out cpu-profile.json
    uv run python scripts/cpu_profile_report.py --stages embedding,ocr
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

STAGE_ORDER = ("embedding", "objects", "ocr", "caption", "faces")


def _rss_bytes() -> int:
    """Resident set size of this process.

    psutil is a dev dependency and is not in the runtime image, so fall back to
    /proc, which is what the containers this runs in actually have.
    """
    try:
        import psutil

        return psutil.Process().memory_info().rss
    except ImportError:
        pass

    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "MB", "GB"):
        if unit == "B":
            if value < 1024 * 1024:
                return f"{int(value)} B"
            value /= 1024 * 1024
            continue
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _make_images(count: int, size: int = 1024):
    """Synthetic images with structure every stage can find something in.

    Real photos would give more representative captions and detections, but they
    cannot be committed, and a run whose inputs differ from machine to machine is
    not a measurement. These are fixed and reproducible: latency is dominated by
    the fixed-size forward pass, not by content. Detection *counts* from this set
    are therefore not meaningful, and the report says so.
    """
    from PIL import Image, ImageDraw

    images = []
    for index in range(count):
        image = Image.new("RGB", (size, size), (240 - index % 40, 240, 245))
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            [size // 8, size // 8, size // 2, size // 2],
            fill=(30 + index % 60, 90, 160),
        )
        draw.ellipse(
            [size // 2, size // 3, size - size // 8, size - size // 4],
            fill=(200, 60 + index % 40, 60),
        )
        draw.text((size // 10, size - size // 6), f"INVOICE {index:04d} TOTAL 42.00")
        images.append(image)
    return images


def _time_stage(fn, images) -> tuple[list[float], int, str | None]:
    """Run `fn` over every image, returning per-image ms, peak RSS, and any error."""
    samples: list[float] = []
    peak = _rss_bytes()
    for image in images:
        started = time.perf_counter()
        try:
            fn(image)
        except Exception as exc:  # noqa: BLE001 - one failing stage must not
            # abort the run; a partial report is still worth having, and the
            # failure itself is a result.
            return samples, peak, f"{type(exc).__name__}: {exc}"
        samples.append((time.perf_counter() - started) * 1000)
        peak = max(peak, _rss_bytes())
    return samples, peak, None


def _percentile(sorted_samples: list[float], fraction: float) -> float:
    if not sorted_samples:
        return 0.0
    index = min(int(fraction * len(sorted_samples)), len(sorted_samples) - 1)
    return round(sorted_samples[index], 2)


def _summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "p50_ms": _percentile(ordered, 0.50),
        "p95_ms": _percentile(ordered, 0.95),
        "min_ms": round(ordered[0], 2) if ordered else 0.0,
        "max_ms": round(ordered[-1], 2) if ordered else 0.0,
        "mean_ms": round(sum(ordered) / len(ordered), 2) if ordered else 0.0,
    }


def _stage_runners() -> dict:
    """Lazy loaders, so a stage that is not measured is never imported."""

    def embedding():
        from find_api.ml.clip_embedder import get_clip_embedder

        return get_clip_embedder().embed_image

    def objects():
        from find_api.ml.object_detector import get_object_detector

        return get_object_detector().detect

    def ocr():
        from find_api.ml.ocr import get_ocr_extractor

        return get_ocr_extractor().extract_text

    def caption():
        from find_api.ml.captioner import get_image_captioner

        return get_image_captioner().generate_caption

    def faces():
        from find_api.ml.face_detector import get_face_detector

        return get_face_detector().detect_faces

    return {
        "embedding": embedding,
        "objects": objects,
        "ocr": ocr,
        "caption": caption,
        "faces": faces,
    }


def _environment() -> dict:
    """Everything needed to decide whether two runs are comparable.

    The protocol in docs/research/search-retrieval-benchmark-plan.md makes the
    same demand of search benchmarks, and for the same reason: latency numbers
    from different hardware must never share a table.
    """
    import os

    info = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "build_profile": os.environ.get("FIND_BUILD_PROFILE"),
        "ml_mode": os.environ.get("ML_MODE"),
        "accel_mode": os.environ.get("ACCEL_MODE"),
    }

    try:
        from find_api.core.hardware import detect_capabilities

        # Field names come from CapabilityReport in core/hardware.py. Spelling
        # them wrong is silent -- getattr's default turns a typo into a
        # plausible "no GPU detected" reading, which is exactly the claim this
        # report exists to substantiate -- so use to_dict() and let the
        # dataclass own the shape.
        info["capabilities"] = detect_capabilities().to_dict()
    except Exception as exc:  # noqa: BLE001 - capability probing is best effort
        info["capabilities_error"] = f"{type(exc).__name__}: {exc}"

    try:
        import torch

        info["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_build": torch.version.cuda,
            "threads": torch.get_num_threads(),
        }
    except Exception as exc:  # noqa: BLE001
        info["torch_error"] = f"{type(exc).__name__}: {exc}"

    return info


def build_report(stages: list[str], image_count: int, warmup: int) -> dict:
    runners = _stage_runners()
    images = _make_images(image_count)
    warmup_images = images[:warmup] if warmup else []

    baseline_rss = _rss_bytes()
    results: dict[str, dict] = {}
    peak_rss = baseline_rss
    previous_rss = baseline_rss

    for stage in stages:
        load_started = time.perf_counter()
        try:
            fn = runners[stage]()
        except Exception as exc:  # noqa: BLE001 - a stage that will not load is
            # the single most important thing this report can surface.
            results[stage] = {
                "status": "load_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        load_ms = (time.perf_counter() - load_started) * 1000

        # Warm up outside the timed window. First-call cost includes lazy weight
        # materialisation and kernel autotuning, and folding that into p50 would
        # overstate steady-state latency by an order of magnitude on some stages.
        first_call_ms = None
        if warmup_images:
            started = time.perf_counter()
            try:
                fn(warmup_images[0])
                first_call_ms = round((time.perf_counter() - started) * 1000, 2)
                for image in warmup_images[1:]:
                    fn(image)
            except Exception as exc:  # noqa: BLE001
                results[stage] = {
                    "status": "warmup_failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "load_ms": round(load_ms, 2),
                }
                continue

        loaded_rss = _rss_bytes()
        samples, stage_peak, error = _time_stage(fn, images)
        peak_rss = max(peak_rss, stage_peak, loaded_rss)

        results[stage] = {
            "status": "ok" if error is None else "run_failed",
            "error": error,
            "load_ms": round(load_ms, 2),
            "first_call_ms": first_call_ms,
            "rss_after_load_bytes": loaded_rss,
            "rss_delta_bytes": max(loaded_rss - previous_rss, 0),
            "peak_rss_bytes": stage_peak,
            "latency": _summarize(samples),
        }
        previous_rss = loaded_rss
        gc.collect()

    return {
        "report_schema_version": 1,
        "environment": _environment(),
        "measurement": {
            "images_per_stage": image_count,
            "warmup_images": warmup,
            "image_source": "synthetic 1024x1024 shapes with rendered text",
            "caveat": (
                "Latency and RSS are real; detection and caption *content* is "
                "not representative, because the inputs are synthetic. Use this "
                "for cost, not for quality."
            ),
        },
        "memory": {
            "baseline_rss_bytes": baseline_rss,
            "peak_rss_bytes": peak_rss,
            "loaded_rss_bytes": previous_rss,
        },
        "stages": results,
    }


def _print_human(report: dict) -> None:
    env = report["environment"]
    print(f"CPU runtime profile - generated {env['generated_at']}")
    print(f"Platform      : {env['platform']} ({env['cpu_count']} cpus)")
    print(f"Build profile : {env.get('build_profile') or '-'}")
    torch_info = env.get("torch") or {}
    if torch_info:
        print(
            f"Torch         : {torch_info.get('version')} "
            f"(cuda_available={torch_info.get('cuda_available')}, "
            f"threads={torch_info.get('threads')})"
        )
    print()

    memory = report["memory"]
    print(f"Idle RSS      : {_human_bytes(memory['baseline_rss_bytes'])}")
    print(f"Loaded RSS    : {_human_bytes(memory['loaded_rss_bytes'])}")
    print(f"Peak RSS      : {_human_bytes(memory['peak_rss_bytes'])}")
    print()

    header = (
        f"{'STAGE':<11} {'STATUS':<13} {'LOAD':>9} {'RSS+':>9} "
        f"{'FIRST':>9} {'P50':>9} {'P95':>9}"
    )
    print(header)
    print("-" * len(header))
    for stage, data in report["stages"].items():
        if data["status"] not in {"ok", "run_failed"}:
            print(f"{stage:<11} {data['status']:<13} {data.get('error', '')}")
            continue
        latency = data["latency"]
        first = data["first_call_ms"]
        print(
            f"{stage:<11} {data['status']:<13} "
            f"{data['load_ms']:>8.0f}m {_human_bytes(data['rss_delta_bytes']):>9} "
            f"{(f'{first:.0f}m' if first else '-'):>9} "
            f"{latency['p50_ms']:>8.0f}m {latency['p95_ms']:>8.0f}m"
        )
        if data["error"]:
            print(f"{'':<11} {data['error']}")

    print()
    print(report["measurement"]["caveat"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the CPU runtime profile's memory and latency cost.",
    )
    parser.add_argument("--images", type=int, default=10, help="images per stage")
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="untimed images run before measurement (0 to include first-call cost)",
    )
    parser.add_argument(
        "--stages",
        default=",".join(STAGE_ORDER),
        help=f"comma-separated subset of: {', '.join(STAGE_ORDER)}",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument("--out", default=None, help="also write JSON to this path")
    args = parser.parse_args(argv)

    if args.images < 1:
        print("error: --images must be at least 1", file=sys.stderr)
        return 2
    if args.warmup < 0:
        print("error: --warmup cannot be negative", file=sys.stderr)
        return 2

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in stages if s not in STAGE_ORDER]
    if unknown:
        print(
            f"error: unknown stage(s) {', '.join(unknown)}; "
            f"known stages: {', '.join(STAGE_ORDER)}",
            file=sys.stderr,
        )
        return 2

    # Measure in the documented order regardless of how they were listed, so RSS
    # deltas stay comparable between runs.
    stages = [s for s in STAGE_ORDER if s in stages]

    report = build_report(stages, args.images, args.warmup)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        if not args.json:
            print(f"\nWrote {args.out}")

    # A stage that could not run is the most important thing this report can
    # surface, and the report is still worth keeping when one does. Exit 1 so a
    # caller notices without having to parse the JSON -- which is how the
    # PaddleOCR oneDNN breakage stayed invisible until a run was read by eye.
    failed = sorted(
        name for name, data in report["stages"].items() if data["status"] != "ok"
    )
    if failed:
        print(f"\nStages did not complete: {', '.join(failed)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
