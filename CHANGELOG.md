# Changelog

All notable changes to Find are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project is
distributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).

## [Unreleased] — App overhaul (`feat/app-overhaul`)

A large feature overhaul bringing reference-grade browsing, albums, sharing,
archive/trash, and a hardware-acceleration layer. All changes below are on the
`feat/app-overhaul` branch and verified by the test suites (backend pytest +
frontend vitest) with a clean `tsc --noEmit` and `ruff check`.

### Added

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
