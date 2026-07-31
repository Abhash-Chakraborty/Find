# PP-OCRv5 Mobile vs Server Benchmark (CPU Deployments)

Resolves: benchmark PP-OCRv5 mobile models for CPU deployments

## Summary

Benchmarked PaddleOCR's `PP-OCRv5_mobile` (det+rec) against the previously
implicit `PP-OCRv5_server` (det+rec) default on CPU, across load time, RAM,
per-image latency, and OCR accuracy on five image categories: photos,
screenshots, receipts, rotated text, and low-contrast text.

**Recommendation: use `mobile` as the CPU-pack default.** It is faster,
uses less RAM, and was at least as accurate as `server` in 4 of 5 test
categories on this benchmark set (see caveats below).

## What changed

- `OCRExtractor` now takes an explicit `variant: "mobile" | "server"`
  (defaults to the new `settings.OCR_VARIANT`, default `"mobile"` based on
  the recorded benchmark results below). Previously, PaddleOCR was
  instantiated with no model names, which silently resolved to the
  `PP-OCRv5_server_det`/`PP-OCRv5_server_rec` models -- the active variant
  was invisible in code and in logs.
- The ModelManager cache key is now variant-qualified
  (`paddleocr:mobile` / `paddleocr:server`), so `get_status()` makes the
  active variant visible directly via `loaded_models`, plus a dedicated
  `runtime.ocr` status block (variant, lang, model names).
- Response shapes (`extract_text`, `extract_text_with_boxes`,
  `extract_text_and_boxes`) are unchanged.

## Benchmark results (CPU, Windows, single run)

| Metric | Mobile | Server |
|---|---|---|
| Load time (cold) | 18.1s | 21.0s |
| RAM after load | 689 MB | 1,145 MB |
| Peak RAM (incl. inference) | 1,063 MB | 1,990 MB |
| New model cache size | 21.1 MB | (already cached; PP-OCRv5 server det+rec combined is roughly 2-3x the mobile pair per PaddleOCR's own docs) |

### Latency by category (mean, ms; 1 warmup + 5 timed runs per image, 4 images/category)

| Category | Mobile | Server | Speedup |
|---|---|---|---|
| photos | 4,398 | 13,765 | 3.1x |
| screenshots | 4,392 | 13,221 | 3.0x |
| receipts | 4,543 | 17,699 | 3.9x |
| rotated | 4,633 | 14,199 | 3.1x |
| low_contrast | 4,410 | 14,039 | 3.2x |

### Accuracy by category (exact-match rate / avg character error rate)

| Category | Mobile | Server |
|---|---|---|
| photos | 75% / CER 0.014 | 0% / CER 0.087 |
| screenshots | 100% / CER 0.0 | 75% / CER 0.031 |
| receipts | 100% / CER 0.0 | 0% / CER 0.074 |
| rotated | 0% / CER 0.917 | 25% / CER 0.735 |
| low_contrast | 100% / CER 0.0 | 0% / CER 0.09 |

Mobile matched or beat server in 4/5 categories. Server's exact-match
misses on photos/screenshots/low_contrast were consistently a missing
space between words (e.g. `"AMOXICILLIN250MG"` vs `"AMOXICILLIN 250MG"`),
not garbled text -- low practical impact for fuzzy-matched downstream
lookups, but worth noting since it explains most of server's CER.

**Rotated text (15-30 degrees) is a shared weak point for both variants**
and should not be read as mobile-specific. This is likely because both
configs run with `use_doc_orientation_classify=False`, which is the
PaddleOCR module responsible for correcting whole-image rotation before
detection runs -- worth a follow-up investigation, out of scope for this
issue.

## Caveats

- Test images (`scripts/generate_test_images.py`) are **synthetic**
  (rendered text + simulated noise/blur/lighting), not real device photos.
  They're reproducible and useful for catching regressions, but real
  photos of medicine strips/receipts should be substituted before treating
  these accuracy numbers as final for production rollout.
- Single benchmark run on one machine (Windows, CPU). Not averaged across
  hardware or repeated runs beyond the 5 timed passes per image.

## Supported languages

Because `OCRExtractor` always passes explicit
`text_detection_model_name`/`text_recognition_model_name` (required to pin
the mobile/server variant), PaddleOCR's `lang` parameter is not used --
passing it alongside explicit model names is silently ignored by
PaddleOCR itself. This means both variants use the **default unified
recognition model**, which supports 5 major text types: Simplified
Chinese, Traditional Chinese, Pinyin, English, and Japanese.

PP-OCRv5 separately offers dedicated recognition models for ~106 more
languages (Korean, Spanish, French, Russian, Thai, Greek, Arabic,
Devanagari, and others), but those are only reachable by dropping the
explicit model names and using `lang=<code>` instead -- which would mean
giving up explicit mobile/server selection. If broader language support
becomes a requirement, that's a separate tradeoff to evaluate (e.g.
per-language explicit model names, since PaddleOCR does publish
language-specific mobile/server pairs like `en_PP-OCRv5_mobile_rec`).

## How to reproduce

```bash
# Optional: regenerate synthetic test images
uv run python scripts/generate_test_images.py

# Speed/RAM/load-time benchmark -> scripts/ocr_benchmark_results.json
uv run python scripts/benchmark_ocr_variants.py

# Accuracy scoring against ground truth -> scripts/ocr_accuracy_results.json
uv run python scripts/score_ocr_accuracy.py

# Test suite
uv run pytest tests/test_ocr.py tests/test_ocr_variants.py -v