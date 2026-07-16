#!/usr/bin/env python3
"""
Score OCR accuracy for mobile vs server PP-OCRv5 variants against the
ground-truth text embedded in scripts/ocr_test_images/**/gt_*.png filenames.

Run with: uv run python scripts/score_ocr_accuracy.py

For each image, ground truth is recovered from the filename (e.g.
"gt_PARACETAMOL_500MG.png" -> "PARACETAMOL 500MG") and compared against the
real OCRExtractor.extract_text() output for both variants using:

  - Exact match (case-insensitive, whitespace-normalized)
  - Character Error Rate (CER): Levenshtein distance / len(ground_truth)

Results are written to scripts/ocr_accuracy_results.json and a summary
table is printed, so the numbers can be pasted directly into the PR as the
"recorded quality results" the issue asks for before recommending a CPU
default.

NOTE: images without a "gt_" prefix (e.g. leftover synthetic_*.png
placeholders) are skipped, since there's no ground truth to score them
against.
"""

import json
import re
from pathlib import Path

from PIL import Image

try:
    import Levenshtein
except ImportError:
    print("This script requires python-Levenshtein. Install with:")
    print("  uv add --dev python-Levenshtein")
    raise SystemExit(1)

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CATEGORIES = ["photos", "screenshots", "receipts", "rotated", "low_contrast"]
IMAGES_DIR = Path(__file__).parent / "ocr_test_images"


def normalize(text: str) -> str:
    """Case/whitespace-insensitive normalization for comparison."""
    return re.sub(r"\s+", " ", text.strip().upper())


def ground_truth_from_filename(path: Path) -> str | None:
    if not path.stem.startswith("gt_"):
        return None
    raw = path.stem[len("gt_"):]
    return raw.replace("_", " ")


def char_error_rate(ground_truth: str, predicted: str) -> float:
    """Character error rate against the best-matching line of a prediction.

    Multi-line images (e.g. receipts) legitimately produce OCR output with
    more text than the single-line ground truth captures (qty/batch lines,
    etc). Scoring against the whole blob would penalize the model for
    correctly reading text the ground truth never claimed to cover, so we
    compare against whichever predicted line is closest instead.
    """
    gt = normalize(ground_truth)
    if not gt:
        return 0.0 if not normalize(predicted) else 1.0

    lines = [normalize(line) for line in predicted.splitlines()] or [""]
    best = min(Levenshtein.distance(gt, line) for line in lines)
    return round(best / len(gt), 3)


def score_variant(variant: str) -> dict:
    from find_api.ml.ocr import OCRExtractor
    from find_api.core.model_manager import get_model_manager

    get_model_manager().reset_for_tests()
    extractor = OCRExtractor(variant=variant)

    results = {}
    for category in CATEGORIES:
        cat_dir = IMAGES_DIR / category
        if not cat_dir.exists():
            continue

        image_scores = []
        for img_path in sorted(cat_dir.glob("gt_*.png")):
            gt_text = ground_truth_from_filename(img_path)
            if gt_text is None:
                continue

            image = Image.open(img_path).convert("RGB")
            predicted = extractor.extract_text(image)

            predicted_lines = [normalize(line) for line in predicted.splitlines()] or [""]
            exact_match = normalize(gt_text) in predicted_lines
            cer = char_error_rate(gt_text, predicted)

            image_scores.append({
                "file": img_path.name,
                "ground_truth": gt_text,
                "predicted": predicted.strip(),
                "exact_match": exact_match,
                "char_error_rate": cer,
            })
            status = "OK " if exact_match else "ERR"
            print(f"    [{status}] {img_path.name}: CER={cer} predicted={predicted.strip()!r}")

        if image_scores:
            exact_matches = sum(1 for s in image_scores if s["exact_match"])
            avg_cer = round(sum(s["char_error_rate"] for s in image_scores) / len(image_scores), 3)
            results[category] = {
                "images_scored": len(image_scores),
                "exact_match_rate": round(exact_matches / len(image_scores), 2),
                "avg_char_error_rate": avg_cer,
                "details": image_scores,
            }

    return results


def main():
    all_results = {}
    for variant in ("mobile", "server"):
        print(f"\n{'=' * 60}\nScoring variant: {variant}\n{'=' * 60}")
        all_results[variant] = score_variant(variant)

    out_path = Path(__file__).parent / "ocr_accuracy_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n{'=' * 60}")
    print("SUMMARY (exact-match rate / avg character error rate)")
    print(f"{'=' * 60}")
    print(f"{'Category':<15} {'Mobile':<20} {'Server':<20}")
    for category in CATEGORIES:
        m = all_results.get("mobile", {}).get(category)
        s = all_results.get("server", {}).get(category)
        m_str = f"{m['exact_match_rate']*100:.0f}% / CER {m['avg_char_error_rate']}" if m else "n/a"
        s_str = f"{s['exact_match_rate']*100:.0f}% / CER {s['avg_char_error_rate']}" if s else "n/a"
        print(f"{category:<15} {m_str:<20} {s_str:<20}")

    print(f"\nFull details written to {out_path}")


if __name__ == "__main__":
    main()