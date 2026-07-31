#!/usr/bin/env python3
"""
Benchmark PP-OCRv5 mobile vs server models for CPU deployments.

Run with:  python scripts/benchmark_ocr_variants.py
Or:        uv run python scripts/benchmark_ocr_variants.py

Measures, for each variant ("mobile" and "server"):
  - Model download/cache size on disk
  - Cold load time (first inference, triggers model load)
  - Peak RAM (resident set size) during load + inference
  - Per-image inference latency (warm, averaged over several runs)

This is a standalone diagnostic script, not a pytest test -- see
tests/test_ocr.py for the automated test suite and
tests/test_ocr_variants.py for the fallback/error-path tests.

Results are written to backend/scripts/ocr_benchmark_results.json so they
can be pasted into the issue/PR as the recorded evidence for recommending
a CPU default (see issue: "benchmark PP-OCRv5 mobile models for CPU
deployments").
"""

import gc
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add src to path so this runs standalone like manual_ocr_check.py does
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import psutil
except ImportError:
    print("This script requires psutil. Install with: uv add --dev psutil")
    sys.exit(1)


VARIANTS = ["mobile", "server"]
WARMUP_RUNS = 1
TIMED_RUNS = 5

# PaddleX/PaddleOCR caches downloaded model weights here by default.
PADDLEX_CACHE_DIR = Path.home() / ".paddlex" / "official_models"


def get_process_rss_mb() -> float:
    """Current process resident set size in MB."""
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


class RssSampler:
    """Continuously sample process RSS on a background thread.

    Sampling only after each call returns misses transient allocations that
    are freed before the call finishes -- most importantly the model download
    and graph construction during the cold load, which is exactly the peak a
    CPU-deployment reader cares about.
    """

    def __init__(self, interval_s: float = 0.05):
        self.interval_s = interval_s
        self.peak_mb = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.peak_mb = max(self.peak_mb, get_process_rss_mb())
            self._stop.wait(self.interval_s)

    def __enter__(self):
        self.peak_mb = get_process_rss_mb()
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._stop.set()
        self._thread.join(timeout=2)
        # Final sample so the peak covers anything since the last tick.
        self.peak_mb = max(self.peak_mb, get_process_rss_mb())
        return False


def dir_size_mb(path: Path) -> float:
    """Calculate the total size of all files in a directory in MB."""
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


def make_test_image(text: str, size=(600, 200), rotate: int = 0) -> Image.Image:
    """Synthetic fallback image generator, used only if no real test images
    are found in scripts/ocr_test_images/. Prefer real photos/screenshots/
    receipts for meaningful accuracy comparisons -- see acceptance criteria.
    """
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default(size=28)
    draw.text((20, size[1] // 2 - 20), text, fill="black", font=font)
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor="white")
    return img


def load_test_images() -> dict:
    """Load benchmark/accuracy images.

    Looks for real images under scripts/ocr_test_images/<category>/*, where
    <category> is one of: photos, screenshots, receipts, rotated,
    low_contrast -- matching the acceptance criteria's comparison
    categories. Falls back to synthetic images for categories with nothing
    on disk, purely so the script is runnable out of the box; synthetic
    images are NOT a substitute for the real accuracy comparison and should
    be replaced with real samples before recording final results.
    """
    categories = ["photos", "screenshots", "receipts", "rotated", "low_contrast"]
    base_dir = Path(__file__).parent / "ocr_test_images"
    images = {}

    for category in categories:
        cat_dir = base_dir / category
        found = []
        if cat_dir.exists():
            for ext in ("*.png", "*.jpg", "*.jpeg"):
                for f in cat_dir.glob(ext):
                    try:
                        found.append((f.name, Image.open(f).convert("RGB")))
                    except Exception as exc:
                        print(f"  ! Skipping unreadable image {f}: {exc}")
        if found:
            images[category] = found
        else:
            print(
                f"  ! No real images found in scripts/ocr_test_images/{category}/, "
                "using a synthetic placeholder. Add real samples for accurate results."
            )
            if category == "rotated":
                placeholder = make_test_image("ROTATED SAMPLE TEXT", rotate=15)
            else:
                placeholder = make_test_image(f"{category.upper()} SAMPLE TEXT")
            images[category] = [(f"synthetic_{category}.png", placeholder)]

    return images


def benchmark_variant(variant: str, test_images: dict) -> dict:
    """Benchmark a specific OCR model variant for load time, RAM usage, and latency."""
    print(f"\n{'=' * 60}")
    print(f"Benchmarking variant: {variant}")
    print(f"{'=' * 60}")

    from find_api.core.model_manager import get_model_manager
    from find_api.ml.ocr import OCRExtractor

    # Fresh state per variant so load time / RAM aren't skewed by a model
    # already cached in the previous iteration.
    get_model_manager().reset_for_tests()
    gc.collect()

    cache_size_before = dir_size_mb(PADDLEX_CACHE_DIR)
    rss_before = get_process_rss_mb()

    category_results = {}

    # Sample RSS continuously from before the load until after the last timed
    # run, so the reported peak includes load-time and inference transients
    # rather than only what is still resident once a call returns.
    with RssSampler() as sampler:
        extractor = OCRExtractor(variant=variant)

        # A tiny image is enough to force the model to load without spending
        # time on real inference for this measurement.
        warm_image = Image.new("RGB", (64, 64), color="white")

        load_start = time.perf_counter()
        extractor.extract_text(warm_image)
        load_time_s = time.perf_counter() - load_start

        rss_after_load = get_process_rss_mb()
        cache_size_after = dir_size_mb(PADDLEX_CACHE_DIR)
        downloaded_mb = max(0.0, cache_size_after - cache_size_before)

        print(f"  Load time:        {load_time_s:.2f}s")
        print(
            f"  RAM after load:   {rss_after_load:.1f} MB "
            f"(+{rss_after_load - rss_before:.1f} MB)"
        )
        print(f"  New cache size:   {downloaded_mb:.1f} MB")

        for category, images in test_images.items():
            latencies = []
            for name, img in images:
                # Warmup run(s) not timed, to separate first-call JIT/graph
                # overhead from steady-state per-image latency.
                for _ in range(WARMUP_RUNS):
                    extractor.extract_text(img)

                for _ in range(TIMED_RUNS):
                    start = time.perf_counter()
                    extractor.extract_text(img)
                    latencies.append(time.perf_counter() - start)

            category_results[category] = {
                "images_tested": [name for name, _ in images],
                "mean_latency_ms": round(statistics.mean(latencies) * 1000, 1),
                "median_latency_ms": round(statistics.median(latencies) * 1000, 1),
                "min_latency_ms": round(min(latencies) * 1000, 1),
                "max_latency_ms": round(max(latencies) * 1000, 1),
            }
            print(
                f"  [{category:>13}] mean={category_results[category]['mean_latency_ms']}ms "
                f"median={category_results[category]['median_latency_ms']}ms"
            )

    peak_rss = sampler.peak_mb

    return {
        "variant": variant,
        "load_time_seconds": round(load_time_s, 2),
        "ram_after_load_mb": round(rss_after_load, 1),
        "ram_delta_load_mb": round(rss_after_load - rss_before, 1),
        "peak_ram_mb": round(peak_rss, 1),
        "downloaded_cache_mb": round(downloaded_mb, 1),
        "latency_by_category": category_results,
    }


def main():
    """Run the complete OCR variant benchmark suite and output results to JSON."""
    print("PP-OCRv5 mobile vs server benchmark (CPU)")
    print(f"PaddleX cache dir: {PADDLEX_CACHE_DIR}")

    print("\nLoading test images...")
    test_images = load_test_images()

    results = {}
    for variant in VARIANTS:
        try:
            results[variant] = benchmark_variant(variant, test_images)
        except Exception as exc:
            print(f"  ! Benchmark failed for variant={variant}: {exc}")
            results[variant] = {"variant": variant, "error": str(exc)}

    out_path = Path(__file__).parent / "ocr_benchmark_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Results written to {out_path}")
    print(f"{'=' * 60}")

    if "mobile" in results and "server" in results:
        m, s = results["mobile"], results["server"]
        if "error" not in m and "error" not in s:
            print("\nSummary (mobile vs server):")
            print(
                f"  Load time:   {m['load_time_seconds']}s vs {s['load_time_seconds']}s"
            )
            print(f"  Peak RAM:    {m['peak_ram_mb']}MB vs {s['peak_ram_mb']}MB")
            print(
                f"  Cache size:  {m['downloaded_cache_mb']}MB vs {s['downloaded_cache_mb']}MB"
            )


if __name__ == "__main__":
    main()
