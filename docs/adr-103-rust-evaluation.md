# ADR: Selective Rust Adoption for Performance-Sensitive Components
 
**Issue:** [#103](https://github.com/Abhash-Chakraborty/Find/issues/103)  
**Related:** [#41](https://github.com/Abhash-Chakraborty/Find/issues/41), [#44](https://github.com/Abhash-Chakraborty/Find/issues/44)  
**Status:** Proposed  
**Date:** 2026-06-29
 
---
 
## Context
 
Find's backend is Python (FastAPI + RQ). Every uploaded image passes through
a single `analyze_image` worker job that runs sequentially:
 
```text
load from MinIO → PIL decode → RGB convert → thumbnail → EXIF
  → object detection (YOLO) → captioning (Florence-2) → OCR (PaddleOCR)
  → hybrid embedding (SigLIP/CLIP) → near-duplicate check → face detection
  → enqueue clustering
```
 
Clustering runs as a separate job: it loads all vectors from PostgreSQL,
runs HDBSCAN, then bulk-writes cluster assignments back.
 
The question this ADR answers: **which parts of that pipeline, if any,
would benefit from a Rust boundary — and is the benefit worth the cost?**
 
---
 
## Component-by-Component Analysis
 
### 1. EXIF Extraction (`utils/exif.py` → `extract_exif_data`)
 
**What it does:** Called once per image in `analyze_image` before the ML
stages. Parses Exif tags from a PIL Image object.
 
**Current state:** Almost certainly uses Pillow's built-in
`image._getexif()` or `ExifTags`, which is pure Python dict iteration over
already-decoded tag data. Very fast; typically < 1 ms per image.
 
**Rust option:** `kamadak-exif` or `rexiv2` via PyO3 — parse raw Exif bytes
directly without going through Pillow's Python layer.
 
**Verdict: No.** EXIF is not a bottleneck. Pillow already wraps libjpeg/
libpng in C for the decode step; the tag-parsing overhead is negligible
next to any ML stage. Adding PyO3 here saves microseconds while costing a
new build dependency and a Rust extension in CI.
 
---
 
### 2. Image Decode and RGB Conversion (`jobs.py` lines ~90–96)
 
```python
image_data = get_file(media.minio_key)   # bytes from MinIO
image = Image.open(io.BytesIO(image_data))
if image.mode != "RGB":
    image = image.convert("RGB")
```
 
**What it does:** Decodes a JPEG/PNG from bytes into a PIL Image for all
downstream ML stages.
 
**Current state:** `PIL.Image.open` and `.convert` already call into
libjpeg/libpng via Pillow's C extension. Pure Python overhead here is a
thin wrapper only.
 
**Rust option:** `image` crate decode via PyO3, returning a NumPy-compatible
buffer.
 
**Verdict: No.** The decode is already native (C). A Rust rewrite would
replace one C library with another at the cost of a PyO3 FFI boundary,
a `maturin` build step, and wheel distribution complexity. No meaningful
gain.
 
---
 
### 3. Embedding Vector Math (`processors.py` — `_safe_normalize_embedding`, weighted fusion)
 
```python
# Called 1–3 times per image (image vec + up to 3 text vecs)
norm = np.linalg.norm(clean_vector)
return (clean_vector / norm).astype(np.float32)
 
# Weighted fusion:
hybrid_vector = sum(
    signal_vectors[name] * (OCR_AWARE_SIGNAL_WEIGHTS[name] / total_weight)
    for name in active_signals
)
```
 
**What it does:** Normalizes and linearly combines up to 4 float32 vectors
(typical dim: 512 or 768). Pure NumPy, runs on CPU.
 
**Rust option:** SIMD-accelerated norm + weighted sum via PyO3 +
`ndarray`/`faer`.
 
**Verdict: No.** NumPy already dispatches to BLAS/OpenBLAS for these
operations. For 512-dim vectors this is < 0.1 ms. The SigLIP/CLIP forward
pass that *produces* those vectors takes 100–500 ms; the fusion is
noise by comparison. Rust here would be unmeasurable.
 
---
 
### 4. `cosine_similarity` in `jobs.py` (near-duplicate check + face cluster matching)
 
```python
def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine similarity for two vectors, guarding empty norms."""
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))
```
 
**Used in:** (a) face cluster name-matching loop — O(named_people) per
cluster label, (b) near-duplicate detection via `duplicate_service`.
 
**Current state:** Pure Python + NumPy dot/norm. Called in a tight loop
during face clustering (`cluster_faces`) over `len(named_person_centroids)`
× `len(unique_labels)` pairs.
 
**Rust option:** Batch cosine similarity matrix via PyO3 + `rayon` parallel
iterator — compute all pairwise scores in one call instead of a Python loop.
 
**Verdict: Maybe, but only if face counts grow large.** At < 1,000 named
people this loop is fast enough. Above ~10,000 faces the Python loop
overhead becomes real. The fix at that scale is a NumPy matrix
multiply (`embeddings @ centroids.T`), which requires zero Rust.
Recommend: **replace the Python loop with a vectorized NumPy approach
first**; only revisit Rust if profiling shows that is still a bottleneck.
 
---
 
### 5. HDBSCAN Clustering (`cluster_images`, `cluster_faces`)
 
```python
embeddings = np.asarray([row.vector for row in media_rows], dtype=np.float32)
clusterer = get_image_clusterer()
labels, info = clusterer.cluster(embeddings)
```
 
**What it does:** Loads all indexed vectors from PostgreSQL into a single
float32 matrix and runs HDBSCAN over them. Run once after every upload
batch.
 
**Current state:** `hdbscan` Python package wraps a Cython core with a
C++ backend. Already fast for ≤ 50k points. The bottleneck at scale is
`O(n²)` approximate nearest-neighbour search, not Python overhead.
 
**Rust option:** Replace with `linfa-clustering` (Rust HDBSCAN) via PyO3.
 
**Verdict: No.** `hdbscan`'s Cython core is already compiled. Linfa's
HDBSCAN is less mature and less tested at scale. No meaningful gain;
real risk of regression.
 
---
 
### 6. Bulk Vector Load for Clustering
 
```python
media_rows = db.query(Media.id, Media.vector).filter(...).all()
embeddings = np.asarray([row.vector for row in media_rows], dtype=np.float32)
```
 
**What it does:** Pulls every stored embedding from PostgreSQL, then builds
a NumPy array via a Python list comprehension. At 10k images with 768-dim
vectors this is ~30 MB of data reconstructed through Python objects.
 
**Rust option:** A PyO3 extension that reads raw bytes from the pgvector
wire format and constructs the float32 matrix directly.
 
**Verdict: Worth investigating at scale, but wrong layer to fix now.**
The correct fix is to use `psycopg2`'s binary protocol or SQLAlchemy Core
with a raw COPY query — zero Rust required. Recommend: **switch to
`np.frombuffer` on raw column bytes** before any FFI.
 
---
 
### 7. ZIP Bulk Upload Extraction
 
Not visible in the pasted files but documented in the README
(`POST /api/upload/bulk`). The upload route extracts ZIP archives before
enqueuing analysis jobs.
 
**Rust option:** PyO3 extension using the `zip` crate with streaming
extraction.
 
**Verdict: Still a legitimate pilot candidate — corrected justification.**
 
An earlier draft of this ADR claimed `zipfile`'s decompression loop is
"pure Python with no C backend." That's incorrect: CPython's `zipfile`
delegates the actual decompression to native modules — `zlib` for
DEFLATE, plus `bz2` and `lzma` for those compression methods — so the
CPU-bound byte-crunching is already C-accelerated.
 
What *is* pure Python, and what a Rust rewrite is actually paying for:
 
- **Per-entry overhead:** parsing each local file header and building a
  `ZipInfo` object in a Python loop over `namelist()`, once per file in
  the archive
- **Chunked I/O round-trips:** `ZipFile.extract()` copies decompressed
  output to disk via Python-level `read()`/`write()` calls in small
  chunks, crossing the Python/C boundary repeatedly for every file
- **Single-threaded extraction:** the whole walk runs under the GIL, so
  a 200-file archive extracts one entry at a time even though
  decompression itself is parallelizable
 
A Rust implementation via the `zip` crate would still call a native
decompressor (`flate2`/`miniz_oxide`) under the hood — it does **not**
make decompression itself faster. The realistic win is collapsing the
whole archive walk into one FFI call (no per-entry Python object churn)
and extracting entries concurrently across threads, which the GIL
prevents today. That's a real but smaller win than the original framing
implied — it scales with **entry count**, not raw byte count, so it
helps bulk uploads of many small files more than a few large ones.
 
- The boundary is still clean (bytes in → files out, no shared state)
- The Rust interface is trivially safe: `fn extract(data: &[u8], dest: &Path) -> Vec<String>`
 
**Recommend:** keep this as the pilot candidate, but benchmark first —
extract a representative bulk-upload archive (e.g. 200 mixed-size files)
with stock `zipfile` vs. a quick PyO3/`zip`-crate prototype before
committing engineering time. If the gain at realistic archive sizes is
under ~20%, this drops from "Pilot" to "Defer."
 
---
 
## Decision Matrix
 
| Component | Real bottleneck? | Rust gain | FFI cost | Contributor risk | Verdict |
|---|---|---|---|---|---|
| EXIF extraction | No | Negligible | Low | Low | **Reject** |
| PIL image decode | No (already C) | None | Medium | Low | **Reject** |
| Vector normalization / fusion | No | None | Low | Low | **Reject** |
| `cosine_similarity` loop | Only at large scale | Low–Medium | Low | Low | **Vectorize in NumPy first** |
| HDBSCAN clustering | No (already Cython/C++) | None | High | High | **Reject** |
| Bulk vector load from DB | At scale only | Low | Medium | Medium | **Fix at DB layer first** |
| ZIP archive extraction | Partial (per-entry overhead + GIL, not raw decompression) | Medium | Low | Low | **Pilot — benchmark first** |
 
---
 
## Where Python Should Stay
 
- **All ML inference** (YOLO, Florence-2, PaddleOCR, SigLIP, InsightFace):
  these already run in C++/CUDA runtimes. Python is only the thin call
  layer. Replacing it with Rust FFI adds complexity with zero runtime gain.
 
- **FastAPI routes and RQ job dispatch**: pure I/O, GIL is irrelevant,
  asyncio handles concurrency correctly.
 
- **SQLAlchemy ORM layer**: already uses C-extension psycopg2. Any
  performance issue here is query design, not Python overhead.
 
- **NumPy vector math**: already BLAS-backed. Rust would replace one
  optimized native library with another.
 
---
 
## Recommended Pilot: ZIP Extraction
 
If the team wants to introduce Rust, the ZIP extractor is the right scope:
 
```text
backend/
  rust/
    find_zip/
      Cargo.toml
      src/
        lib.rs     # PyO3 module exposing extract_zip_bytes()
  pyproject.toml   # maturin build backend alongside uv
```
 
```rust
// src/lib.rs (sketch)
use pyo3::prelude::*;
use std::io::Cursor;
use zip::ZipArchive;
 
#[pyfunction]
fn extract_zip_bytes(data: &[u8], dest: &str) -> PyResult<Vec<String>> {
    let cursor = Cursor::new(data);
    let mut archive = ZipArchive::new(cursor)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
    // ... stream each entry to dest/
}
 
#[pymodule]
fn find_zip(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_zip_bytes, m)?)?;
    Ok(())
}
```
 
The upload route keeps a pure-Python `zipfile` fallback so the light stack
(`ML_MODE=mock`) and contributor setups without Rust work unchanged.
 
**CI change:** Add `maturin build --release` step; publish wheel alongside
the Python package. The Rust extension is optional — absence falls back to
Python silently.
 
---
 
## What Would Change This Analysis
 
| Evidence | Changes what |
|---|---|
| Flamegraph showing face cosine loop > 5 % of `cluster_faces` wall time | Promotes vectorized NumPy rewrite; Rust only if NumPy still insufficient |
| Bulk vector load from DB shown to exceed 1 s at target scale | Promote DB-layer fix first; Rust as last resort |
| Adoption of Tauri for desktop app (#41) | A small Rust sidecar to manage PostgreSQL/Redis/MinIO process lifecycle becomes idiomatic and recommended — zero impact on Python stack |
| A contributor already experienced with PyO3 | Lowers FFI cost estimate; makes the cosine-similarity batch helper worth doing earlier |
| Benchmark shows < 20% improvement extracting a representative bulk-upload archive | Downgrades ZIP extraction from "Pilot" to "Defer" — decompression is already native, so the remaining per-entry/GIL win isn't worth the FFI cost |
 
---
 
## Summary
 
Rust is not warranted as a broad initiative. The ML inference dominates
`analyze_image` wall time by orders of magnitude, and all supporting
math is already BLAS/Cython-backed. The one genuine candidate today is
**ZIP extraction** — not because decompression itself is slow in
Python (it already calls native `zlib`/`bz2`/`lzma`), but because the
per-entry Python overhead and GIL-bound single-threaded extraction loop
have a clean, low-risk FFI boundary and a real benefit on bulk uploads
of many small files. This should be confirmed with a quick benchmark
before committing engineering time.
 
Everything else should be fixed at the correct layer first (vectorized
NumPy, binary DB reads, query optimization) before introducing FFI
complexity.