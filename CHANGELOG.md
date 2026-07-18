# Changelog

All notable changes to Find are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project is
distributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).

## [Unreleased]

### Changed

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
