# Changelog

All notable changes to Find are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project is
distributed under AGPL-3.0 (see `LICENSE` / `NOTICE`).

## [1.1.4] — 2026-10-26

### Changed

- perf: page person, cluster and album photo lists (bae3395)
- chore(deps): move torch to 2.13.0 on the CUDA 12.9 index (6e5e6ae)
- test: time the layout scaling check on its fastest run (480b652)
- perf: compute ranking boosts in one UPDATE (b4d3a4c)
- perf: look up cluster members once for the whole list (e77e610)
- perf: count album members in one query (10affa5)
- docs: changelog for search, list and polling performance (237105a)
- perf: poll clusters and people only while images index (1c149a7)
- fix: stop the upload monitor polling in a tight loop (bfe39d4)
- perf: let search use the HNSW index (dbadfca)
- fix: create the HNSW vector index at startup (e8e9edc)
- perf: stop presigning every row in gallery, search and clusters (3aaa155)
- perf: defer vector columns so lists don't load embeddings (7d38ea4)
- chore(deps): patch backend advisories in uv.lock (a2d6f41)
- chore(deps): patch undici and vite advisories in the frontend (1ab32c9)
- docs: changelog for the 1.1.4 fixes and cleanup (0aea08e)
- chore: enable ruff's simplify rules on the backend (abc24b6)
- chore: chain re-raised exceptions and enable bugbear (5ffc237)
- chore: modernise backend type hints with pyupgrade (b8323a5)
- chore: sort backend imports with ruff (b389726)
- docs: name BLIP as the caption model (2c4345c)
- fix: report caption and OCR models as loaded in the footprint (40b82f7)
- refactor: drop unused frontend helpers and packages (ce04eeb)
- refactor: remove backend code nothing calls (4bb5588)
- chore: remove the root plan.md work log (dda5645)
- ci: remove the TestSprite workflow (cec4f94)
- fix: show new uploads in the gallery right away (5440ff6)
- fix: let Retry analysis recover a failed OCR load (66453eb)
- fix: reload a warm model when its configuration changes (3f68e2a)
- fix: unlock protected shares once instead of per photo (a642a94)
- fix: keep archived and trashed photos out of Clusters and People (66d06e6)
- fix: match JPEGs in the search file-type filter (7b6b785)
- chore(deps): consolidate open dependency updates (#504) (f3eda56)
- chore(deps): bump the frontend-runtime group across 1 directory with 21 updates (#503) (de5135f)
- chore(deps): bump the desktop-runtime group (#487) (855e8fd)
- chore(deps): bump the actions group across 1 directory with 8 updates (#502) (ed25585)
- docs: rework the README around a real search demo (9a5c6e2)
- feat: PR Docker builds, desktop release path, PWA offline queue, and Instance UI (#464) (3b94323)
- test: move OCR logic tests out of paddle-dependent suite (#451) (5e5ecf1)
- chore(deps): bump the python-runtime group across 1 directory with 4 updates (#461) (89990e9)
- chore(deps): update uvicorn[standard] requirement to >=0.52.3,<0.53 (#463) (4beabe9)
- fix(api): stop echoing identifier-resolution errors into the footprint report (#462) (b854237)
- fix(deps): raise pnpm overrides past the open nanoid, postcss, and undici advisories (#460) (6bb44be)
- chore(deps-dev): bump setuptools from 83.0.0 to 84.0.0 in /backend in the python-runtime-major group (#456) (cbc0d40)
- chore(deps): bump the python-runtime group in /backend with 4 updates (#455) (67f40aa)
- chore(deps-dev): bump ruff in /backend in the python-tooling group (#454) (32edda6)
- chore(deps): bump the frontend-runtime-major group across 1 directory with 3 updates (#458) (6a880f3)
- chore(deps): bump astral-sh/setup-uv in the actions-major group (#453) (a3347ec)
- fix: record `upload.completed` only once the job has actually finished (#447) (fa4cb61)
- fix: recover from a file_hash race during upload instead of poisoning the session (#445) (3ba0f63)
- fix: batch list_people's per-person queries into one (#446) (b2cdd6e)
- Test: image preview modal coverage (#448) (d03e717)
- chore(deps): bump the python-runtime group across 1 directory with 3 updates (#450) (e5ef06b)
- chore(deps): update uvicorn[standard] requirement in /backend (#442) (85380c0)
- chore(deps): bump cryptography (#441) (3fb2601)
- chore(deps): bump the frontend-runtime group in /frontend with 5 updates (#443) (fa04906)
- chore(deps): bump the actions group with 2 updates (#439) (6fa2fd4)
- chore(frontend): port tailwind.config.js to CSS-first @theme (#436) (83bf03a)
- feat: implement the Track C ranking matrix for the search benchmark (#99) (#433) (77df243)
- feat: make the CPU runtime profile build, run, and report its cost (#339) (#432) (0a0c262)
- feat: measure HNSW index fidelity (Track A of #99), and correct the recall concern (#431) (783b9b4)
- feat: add offline search evaluation harness (#430) (1098e6d)
- feat: improve UI and fix responsive layout (#412) (40fcb16)
- docs: research notes for encrypted BYO storage sync (#187) and search benchmarking (#99) (#429) (9e98b8e)
- feat: add model cache and runtime footprint report (#359) (76456e4)
- feat: generate privacy-safe local diagnostics bundle (#428) (e95bd53)
- chore(deps): bump the frontend-runtime-major group across 1 directory with 4 updates (#427) (ff0b9d5)
- chore(deps-dev): bump the python-tooling group across 1 directory with 2 updates (#423) (c93796f)
- chore(deps): update uvicorn[standard] requirement in /backend (#425) (0e5707c)
- chore(deps): bump next in /frontend in the frontend-runtime group (#426) (ff20ddf)
- chore(deps): bump the python-runtime group in /backend with 3 updates (#424) (5a5ff8d)
- feat(settings): add an About card, and finish the open a11y gaps (#411) (ea1ca1b)
- feat: add Activity timeline UI (#376) (1a2490b)
- feat: add privacy-safe local activity log (backend) (#367) (2c17c82)
- fix(ml): serialize embed_text output as native floats (#409) (c259f47)
- perf(ocr): benchmark and default to PP-OCRv5 mobile for CPU deployments (#364) (81b11e1)
- feat: implement remote ML client and API endpoints (#365) (78f92cb)
- chore(deps): bump the python-runtime group across 1 directory with 19 updates (#408) (13153fa)
- chore(deps): bump the python-runtime-major group across 1 directory with 4 updates (#407) (755ffde)
- chore(deps): bump axios (#406) (14c7d1a)
- chore(ci): split linters out of the Dependabot runtime groups (#405) (fd08205)
- chore(deps): update uvicorn[standard] requirement in /backend (#403) (20f6eb1)
- docs: add environment setup note for Docker installation (#366) (995a9ef)
- chore(ci): move backend Dependabot to the uv ecosystem (#395) (64cda0e)
- chore(deps): bump the desktop-runtime group (#386) (a0a1dfe)
- chore(deps): bump the actions-major group with 2 updates (#394) (4b38969)
- chore(deps): bump the actions group with 2 updates (#392) (c6c5ff2)
- chore(deps): bump the frontend-runtime group across 1 directory with 11 updates (#393) (afa464c)
- chore(ci): split Dependabot majors from minors and pin torch to manual bumps (#384) (cd28d0e)
- fix: constrain transitive setuptools to the patched release (#381) (7bbe9ba)
- fix: collapse postcss onto a single patched version (#379) (288a780)
- fix: close open dependency advisories across all three ecosystems (#377) (6dad696)
- chore(deps-dev): bump setuptools from 82.0.1 to 83.0.0 in /backend (#373) (357bce9)
- chore(deps): bump axios from 1.16.0 to 1.18.0 in /frontend (#371) (96d667f)
- chore(deps): bump pillow from 12.2.0 to 12.3.0 in /backend (#372) (ee5b787)
- chore(deps): bump serde_with in /frontend/src-tauri (#363) (109cf97)
- chore(deps): bump the actions group with 11 updates (#368) (f5c40c2)
- ci: establish canary release governance (162cb44)
- fix: regenerate modular dependency lock (a307cbd)
- fix: align ONNX CUDA runtime for v1.1.3 (d75ce6b)
- feat: restore fullscreen previews and persistent uploads (64f4c0e)
- test: align settings smoke assertion (17aab0e)
- fix: render the offline map reliably (7dae931)
- chore: release version 1.1.2 (edd2d01)
- feat: add modular runtime and trash controls (fdbf7c8)
- feat: complete timeline and route interactions (591e9f4)
- chore: release version 1.1.1 (891af0a)
- feat: modernize shell settings and search (c74fed6)
- feat: add recoverable private vault controls (215ccc0)
- fix: harden runtime and media paths (125ba26)
- chore(deps): bump transformers from 5.3.0 to 5.5.0 in /backend (3191162)
- fix: secure the full AI caption pipeline (2836f91)
- fix: restore media previews and Florence AI (361a002)
- fix: align runtime contracts and privacy guidance (853b593)
- docs: prepare the v1.1 release candidate (16bd8d2)
- ci: validate and publish modular release profiles (5315afe)
- build: split modular runtime artifacts (fba69cd)
- feat: ship the timeline-first application experience (430035f)
- feat: add accounts maps vault and runtime controls (c787c61)
- fix: make upload pixel validation thread-safe (#352) (de5f279)
- fix: cap multipart uploads at configured file limit (#351) (8f71653)
- Design model pack cache/download contract for installer mode (#350) (d4b4332)
- docs: clarify the reset command discards staged changes too (review) (03867e6)
- docs: one-time re-checkout note for pre-.gitattributes Windows clones (5121e8d)
- ci: normalize text line endings so Biome passes on Windows (8e7ab62)
- fix: complete full-stack review follow-up (a680ee0)
- refactor: address storage review feedback (311b4ab)
- fix: harden Docker builds and local runtime (c43d5c0)
- chore(deps): bump pip from 26.1.1 to 26.1.2 in /backend (e0afe15)
- chore(deps): bump onnx from 1.21.0 to 1.22.0 in /backend (175b8f3)
- chore(deps): bump transformers from 4.57.6 to 5.3.0 in /backend (80ff94d)
- ci: add manual GHCR publish workflow (6ff9cce)

## [Unreleased]

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
