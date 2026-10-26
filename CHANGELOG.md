# Changelog

All notable changes to Find are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project is
distributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).

## [Unreleased]

## [1.1.5] — 2026-10-26

### Fixed

- The `cpu` backend image builds for linux/arm64 again. paddlepaddle 3.3 has
  no Linux ARM wheel, so arm64 uses 3.2.2 and x86_64 keeps 3.3.1. CI now
  resolves the cpu extra for arm64 on every change, so this fails before a
  release instead of during one.

### Changed

- Releases publish as soon as the canary promotion lands on `main`. The
  three-hour quiet period and the emergency input are gone.

## [1.1.4] — 2026-10-26

### Fixed

- Search's file-type filter matches JPEGs again; `jpg` and `jpeg` map to
  `image/jpeg`, the same as in the gallery.
- Archived and trashed photos no longer appear in Clusters or People.
- Photos in a password-protected share load again. A correct password sets a
  12-hour unlock cookie for that link, so thumbnails no longer need the
  password or run a bcrypt check each.
- Switching between CPU and GPU reloads models that are already in memory
  instead of keeping the old copy until the worker restarts.
- Retry analysis can recover a failed OCR model load.
- New uploads appear in the gallery as soon as they finish.
- The model footprint report shows the caption and OCR models as loaded when
  they are.
- Compose installs create the vector index at startup. Before, only Alembic
  created it, and compose never runs Alembic, so every search read the whole
  table.
- The upload monitor polls running jobs every 2.5 s. It used to poll again
  after every response, so a large batch hit the job endpoint back to back.

### Security

- torch 2.13.0 and torchvision 0.28.0 close two PyTorch memory-corruption
  advisories. The NVIDIA build now pulls CUDA 12.9 wheels, since the CUDA
  12.8 index stops at torch 2.11.
- Patched backend and frontend dependencies with open advisories. The
  desktop app's glib advisory waits on Tauri moving past gtk 0.18; Find doesn't
  call the affected API.

### Removed

- The TestSprite workflow, which sent the app to a hosted test service.
- `plan.md`, `POST /cluster/trigger` (use `/cluster/run`), unused backend and
  frontend helpers, and four unused npm packages.

### Changed

- Search ranks the closest 200 or more images through the vector index, then
  applies the threshold and feedback boost. On 20,000 test vectors a query
  took 4.2 ms instead of 203 ms. The match count now counts within that pool.
- Gallery, search and cluster lists no longer load embeddings or
  sign a storage URL per photo; they link to the app's own image routes.
- A person, a cluster or an album opens with its first 200 photos and a
  Load more button, instead of sending every photo in one response. The
  cluster filename filter now searches all members, not only loaded ones.
- Clusters, People and the AI runtime card stop polling on an idle library.
  They refresh while images index, during a clustering job, and on focus.
- Docs name BLIP as the caption model.
- The backend lints with import sorting, pyupgrade, bugbear and simplify
  rules, and re-raised exceptions keep their cause.
- Contributor work now targets a protected `canary` default branch; only the
  reviewed canary promotion can enter `main`.
- Release preparation synchronizes every version surface and uses one manual
  patch/minor/major selector, followed by a restartable three-hour release gate.
- CI actions are immutable-SHA pinned, dependency updates target canary, and
  release images include provenance and software bill-of-material attestations.

## [1.1.3] — 2026-07-15

### Fixed

- NVIDIA workers now use a CUDA 12/cuDNN 9-compatible ONNX Runtime and preload
  the CUDA libraries installed with PyTorch before InsightFace creates model
  sessions, preventing repeated `libcublasLt.so.11` errors and CPU fallback.
- Full-screen previews retain their complete action and metadata toolset, and
  upload/indexing progress persists across routes until successful completion.

## [1.1.2] — 2026-07-14

### Added

- Addressable `/image/{id}` previews that retain the originating library route,
  lock background scroll, expose metadata, and provide contextual archive,
  trash, restore, or album-removal actions.
- Album photo picker with recent and semantic-search modes, plus automatic
  trash retention controls for 7, 30, 90, custom, or never-delete policies.

### Changed

- Timeline pages use the date scrubber as their only visible scrollbar and
  suppress it when the library cannot scroll.
- Album sharing is hidden until requested; route headers, upload, account,
  search, duplicates, clusters, and people use a compact visual hierarchy.
- AI-dependent controls now report disabled or non-installed artifacts
  truthfully, including unavailable GPU selection in modular CPU/no-AI builds.

### Fixed

- Full-resolution previews, modal navigation URLs, body scroll containment,
  archive/trash restoration, and single-image timeline presentation.
- Blank private-map canvases in browsers that do not render worker-sourced
  GeoJSON fills; bundled Natural Earth geometry now has a local SVG fallback.

## [1.1.1] — 2026-07-14

### Added

- Guided vault setup and unlock, one-time recovery codes, password and recovery
  rotation, and configurable automatic locking.
- Collapsible desktop navigation with a compact header and universal search
  across photos, albums, routes, and settings.

### Changed

- Account, vault, search, and settings controls now share the local-first v1.1
  application shell and remain usable across responsive layouts.

## [1.1.0] — 2026-07-13

A product and platform overhaul bringing timeline-first browsing, account and
vault management, a private offline map, modular AI artifacts, and a polished
responsive application shell.

### Added

**Application shell and account**
- Responsive sidebar/top bar, focus-safe mobile navigation, global search
  shortcut, theme persistence, and consistent route-level spacing.
- Setup, login, profile, password rotation, active-session listing, and session
  revocation backed by secure HTTP-only session cookies.

**Private map and vault**
- Opt-in EXIF GPS retention with an account-scoped offline MapLibre view using
  bundled Natural Earth geometry and no external tile or geocoding requests.
- Explicit vault session locking, session-only decrypted thumbnails, timeline
  browsing, full-screen preview, and rollback-safe restoration.

**Modular runtime**
- Separate no-AI, mock, CPU, and NVIDIA dependency artifacts. CPU/no-AI builds
  do not install CUDA packages; the dashboard reports the installed artifact,
  applied mode, worker health, and restart requirements.
- Dashboard selection of disabled, mock, or full processing whenever that mode
  is installed in the active artifact, without restarting or downloading a
  different dependency stack.
- Consolidated Compose topology: `compose.yml`, `compose.base.yml`, and explicit
  `compose.no-ai.yml`, `compose.mock.yml`, and `compose.cpu.yml` profiles.
- Tag-driven and manual GHCR publishing for immutable web images and all four
  modular backend profiles.

**Timeline**
- Month-bucketed timeline API: `GET /api/timeline/buckets` (counts per month)
  and `GET /api/timeline/bucket` (columnar per-asset window with aspect ratio).
- React timeline page (`/timeline`) with a justified (variable-row) grid,
  virtualized rendering, a fast date-scrubber scrollbar with segment preview,
  and a full-screen asset viewer (zoom/pan, keyboard nav, slideshow).

**Albums**
- Album model + endpoints: create/list/get/update/delete, membership
  (add/remove), cover image, and manual ordering.
- Albums UI: list/create page (`/albums`), detail page (`/albums/[id]`) with
  asset grid, set-cover, remove, delete, and an in-page asset viewer.
- "Add to album" from the gallery's multi-select action bar (pick an existing
  album or create one).

**Sharing**
- Secure album shared links: random CSPRNG key stored only as a SHA-256 hash,
  optional bcrypt password, server-enforced expiry, and `allow_download` /
  `show_exif` flags. Public access is scoped to exactly the linked album and
  served through share-scoped byte routes (no raw storage keys exposed).
- Sharing UI: share-link management on the album detail page and a public
  shared-album view (`/public/shared/[key]`) with password gate.

**Archive & Trash**
- `media.is_archived` + `media.deleted_at` (soft delete). Archive/trash/restore
  /empty-trash endpoints; `/archive` and `/trash` pages; move-to-archive and
  move-to-trash actions in the gallery selection bar.

**Hardware acceleration**
- `ACCEL_MODE` setting (`auto` / `gpu` / `cpu`) with **automatic CPU fallback**;
  capability detection (`GET /api/config/hardware`) across ONNX execution
  providers (CUDA/ROCm/CoreML/DirectML) and torch CUDA/MPS. Wired into all ML
  inference (embedding, captioning, object & face detection). Settings panel
  (`/settings`) toggle. See `docs/guides/hardware-acceleration.md`.

### Changed
- Gallery, search, timeline, and album asset listings adopt a single browse
  scoping rule: an asset is shown only when **not hidden, not archived, and not
  trashed**. Single-item lookups are unaffected (so archive/trash detail views
  still open).
- ML model-cache keys now include `ACCEL_MODE` so switching mode reloads cleanly.

### Fixed
- Two import-time monkeypatch leaks in the backend test suite (`test_reprocess`
  rebinding `gallery.Media`; `test_migrate_db` shimming `sys.modules`'
  config module) that polluted the full-suite run. The backend suite now runs
  green end-to-end without ignoring any files.
- Type-safety + lint cleanups across new frontend/backend code (`tsc --noEmit`
  and `ruff check` clean).

### Notes
- This overhaul reuses UI/behavior patterns from an AGPL-3.0 reference project;
  derived files carry attribution and Find is distributed under AGPL-3.0
  (`NOTICE`).
- See `MIGRATION.md` for upgrade steps (database migrations + new env var).
