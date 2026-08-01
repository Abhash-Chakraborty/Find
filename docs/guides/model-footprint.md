# Model Footprint Report

Before changing ML model defaults, adding an installer, or writing a
benchmark, you need a straight answer to "what does this actually download
and load?" This report gives you that answer without guessing at cache
paths or hand-measuring directories.

It's the measurement source for
[#45 — design installer model downloads and cache management](https://github.com/Abhash-Chakraborty/Find/issues/45)
and for model benchmark issues: don't propose new defaults or pack sizes
without running this first.

## What it reports, per model

- **Identifier** — the exact model/checkpoint configured via settings
  (e.g. `microsoft/Florence-2-base`, `yolo26n.pt`).
- **Cache footprint** — whether it's on disk, total bytes, file count, and
  when it was last modified.
- **Loaded state** — whether it's currently loaded in this process (or any
  process that has published status to Redis).
- **Device / provider** — CPU, CUDA, MPS, or the resolved ONNX execution
  provider, from the same detection `find_api.core.hardware` uses (see
  [hardware-acceleration.md](./hardware-acceleration.md)).
- **Last-use time** — from the in-process `ModelManager`; this is
  local-process-only, not aggregated across workers.

Nothing here downloads a model. Cache lookups are local filesystem reads or
local cache-*index* reads (`huggingface_hub.scan_cache_dir()` reads on-disk
metadata only). Every resolver degrades to "not cached" on failure instead
of raising — a missing library or unset cache dir never breaks the report.

## Running it

```bash
cd backend
uv run python scripts/model_footprint_report.py            # human-readable table, with paths
uv run python scripts/model_footprint_report.py --json      # JSON, with paths
uv run python scripts/model_footprint_report.py --no-paths  # either mode, no filesystem paths
```

This is a **local CLI tool** — it prints cache paths by default because it
runs with your own filesystem access. The equivalent API endpoint does not:

```http
GET /api/status/models/footprint   (admin-only)
```

The API response never includes filesystem paths, arbitrary host
information, or anything about media/user data — only sizes, counts,
identifiers, and timestamps. If you need paths from a deployed instance,
use the CLI script on that machine directly; don't add paths to the API
response.

## Runtime packs

Find's models fall into three groups, used to reason about install size:

| Pack | Contents | Status |
|---|---|---|
| **light** | SigLIP embedding model only (text/image search — the core feature) | Implemented; measured by this report |
| **full** | SigLIP + Florence-2 captioning + YOLO object detection + InsightFace + PaddleOCR | Implemented; measured by this report |
| **proposed_cpu** | CPU-optimized ONNX replacements: CLIP ViT-B-32 (ONNX), InsightFace `buffalo_s` (ONNX), PP-OCRv5 mobile (ONNX) | **Not implemented.** Tracked by [#339](https://github.com/Abhash-Chakraborty/Find/issues/339). The report lists these models by name with `status: "not_implemented"` and no size, since there's nothing on disk yet to measure. |

The report's `packs` section gives you `cached_count` / `total_count` and
summed `bytes_on_disk` for `light` and `full` directly from your machine's
actual cache — always trust that over any number in this doc, including the
ones below.

### Approximate current sizes (for planning only — re-run the script for ground truth)

These are public, approximate download sizes for the currently-configured
checkpoints, gathered for rough installer-size planning. They are **not** a
substitute for running the report on a real machine, and will drift as
models/versions change:

| Model | Pack | Approx. size |
|---|---|---|
| SigLIP (`ViT-B-16-SigLIP`/`webli`) | light, full | ~0.4–0.8 GB depending on precision |
| Florence-2-base | full | ~0.46 GB (safetensors) |
| YOLO (`yolo26n.pt`, nano) | full | a few MB |
| InsightFace `antelopev2` | full | ~0.4 GB |
| PaddleOCR (en, det+rec+cls) | full | tens of MB |

Rough full-pack total: **on the order of 1.5–2 GB**. This is exactly the
kind of number the installer work in #45 needs pinned down precisely — use
`model_footprint_report.py` against a real, fully-loaded cache rather than
this table when it matters.

### Proposed CPU pack

Not implemented. `buffalo_s` (InsightFace's smaller ONNX face pack) is
publicly documented at roughly 0.16 GB versus `antelopev2`'s ~0.4 GB — a
meaningful reduction, which is the whole motivation for the proposed pack.
Once ViT-B-32 (ONNX) and PP-OCRv5 mobile are actually wired up, add real
cache-resolver entries to
`backend/src/find_api/core/model_footprint.py::PROPOSED_CPU_MODELS` and this
row moves from "proposed" to "measured" like the other two packs.

## Extending the report

Model definitions live in `backend/src/find_api/core/model_footprint.py` as
a tuple of `ModelSpec` entries: a manager key, display label, pack
membership, an identifier function, a cache resolver, and a device
resolver. To add a model:

1. Add a `resolve_<name>_cache()` function that finds the on-disk footprint
   for that library (best-effort, wrapped so it can never raise).
2. Add a `ModelSpec` entry to `MODEL_SPECS` referencing it.
3. Add tests in `backend/tests/test_model_footprint.py` using a temporary
   fake cache directory — never a real download — following the existing
   `Test*Cache` classes as a template.
