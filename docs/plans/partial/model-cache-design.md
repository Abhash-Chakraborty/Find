# Model Pack Cache & Download Design (Installer Mode)

**Status:** Draft — design + thin interfaces only
**Related:** [Issue #45](https://github.com/Abhash-Chakraborty/Find/issues/45), [local-first-roadmap.md](./local-first-roadmap.md)

## Goal

Let Find ship a small installer while still running ML fully locally after
first use. Models are not bundled in the installer and are not downloaded
silently — the user explicitly chooses what to download, sees size/progress,
and can cancel, retry, and work fully offline afterward.

## Current state (verified against source)

Find has 5 ML capabilities, each with its own model source and no shared
cache/version concept today:

| Category   | Loader file                       | Model identifier(s)                                  |
|------------|------------------------------------|--------------------------------------------------------|
| Embeddings | `ml/clip_embedder.py`             | `settings.CLIP_MODEL` (`ViT-B-16-SigLIP`) + `settings.CLIP_PRETRAINED` (`webli`), via open_clip |
| Caption    | `ml/captioner.py`                 | `settings.BLIP_MODEL` (`microsoft/Florence-2-base`), via HF `from_pretrained` |
| Objects    | `ml/object_detector.py`           | `settings.YOLO_MODEL` (`yolo26n.pt`), Ultralytics auto-download |
| OCR        | `ml/ocr.py`                       | PaddleOCR, `lang="en"`, own internal cache dir |
| Faces      | `ml/face_detector.py`             | InsightFace `antelopev2` (has a known nested-folder extraction quirk already handled in code) |

`core/model_manager.py` only manages in-memory lifecycle (lazy load, LRU
eviction, idle unload). It has no concept of "on disk," "downloaded," or
"version" — this design adds that layer above it, without touching it.

## Versioned pack manifest

Each pack (see `core/model_pack.py::ModelPack`) records:

- `pack_id`, `category`, `version`
- `source_url`, `license`
- `size_bytes` (shown to user before download)
- `checksum_sha256` (verified after download and on every load)
- `compatible_app_versions`
- `config_key` — mirrors the existing loader `config_key` format already
  used by `ModelManager.get_model()`, so a pack swap can invalidate an
  in-memory model the same way a config change does today.

Manifests will initially live as static JSON (or Python data) shipped with
the app; a remote-updatable manifest is out of scope for this PR.

## First-run selection & download UX

1. On first run, show each category (Embeddings/Caption/Objects/OCR/Faces)
   with its pack size and license.
2. Preflight: check free disk space against sum of selected pack sizes
   before starting any download; block with a clear message if insufficient.
3. Per-pack progress (bytes downloaded / total), an overall progress
   summary, and a cancel button per pack.
4. Cancel leaves the pack `NOT_INSTALLED` (no partial pack is ever marked
   installed).
5. Resume: partial downloads are resumable across app restarts by keeping
   the partial file plus a small sidecar state file recording bytes-so-far;
   if the sidecar is missing/corrupt, restart the download instead of
   guessing.
6. Retry: failed downloads move to `PackStatus.FAILED` with a stored error
   and a manual retry action; automatic retry uses capped exponential
   backoff (not implemented in this PR).

## Atomic install & corrupted-cache recovery

- Download to a temp path inside `MODEL_CACHE_DIR` (e.g. `<pack_id>.part`).
- Verify SHA-256 against the manifest.
- Atomically rename into the final cache path only after verification
  succeeds.
- Mark `PackStatus.INSTALLED` only after the rename succeeds.
- On every subsequent load, `PackCache.verify()` re-checks the checksum
  cheaply (or on a cadence, to avoid hashing large files every launch);
  a failed verify moves the pack to `PackStatus.CORRUPTED`, quarantines
  the bad file, and re-offers download instead of crashing the loader.

## Cache location & offline reuse

- New setting `MODEL_CACHE_DIR` (`config.py`) — empty string means "resolve
  a platform-appropriate app-data/cache directory at the call site."
- New setting `ML_OFFLINE_ONLY` (`config.py`) — when true, a pack cache
  implementation must refuse any network call and rely solely on what
  `PackCache.is_installed()` confirms is already verified on disk.
- Underlying libraries have their own cache conventions (HF `HF_HOME` for
  Florence-2, Ultralytics' own weights directory, PaddleOCR's internal
  cache dir, InsightFace's `~/.insightface`). The install-mode cache should
  point these at subdirectories of `MODEL_CACHE_DIR` via their respective
  env vars, rather than reimplementing per-library caching. This mapping is
  a follow-up implementation task, not covered by the thin interfaces in
  this PR.

## Preserving existing dev modes

- `ML_MODE=mock` / `ML_MODE=full` under Docker are unaffected: the pack
  cache is additive infrastructure primarily consumed by future installer
  (Tauri) flows, not a requirement for contributor/dev workflows.
- `ML_MODE=remote` is untouched — remote mode does not need local packs.

## Thin interfaces added in this PR

See `backend/src/find_api/core/model_pack.py`:

- `ModelPack` (frozen dataclass) — the manifest shape.
- `PackCategory`, `PackStatus` — enums.
- `PackProgress` — progress/status snapshot.
- `PackCache` (Protocol) — the cache contract: `is_installed`, `status`,
  `install`, `verify`, `remove`.
- `NotImplementedPackCache` — placeholder so other code can type against
  `PackCache` before a real backend exists.

**No existing loader in `find_api/ml/` is modified by this PR.** A real
`PackCache` implementation, and wiring loaders to consult it, is explicitly
out of scope here and should be a follow-up issue once this contract is
agreed.

## Out of scope for this PR

- Bundling any model weights into the installer.
- Any silent/automatic download.
- Replacing or modifying any of the 5 existing ML loaders.
- A real filesystem-backed `PackCache` implementation.
- Tauri-side UI/IPC for the download screen (tracked separately in the
  local-first roadmap's Phase 2).

## Open questions for maintainer review

- Should pack manifests be bundled at build time or fetched from a remote
  index? (This design assumes bundled/static for the first version.)
- Should `MODEL_CACHE_DIR` also apply to Docker/full mode, or stay
  installer-only?