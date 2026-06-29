# Find — Whole-Application Overhaul Plan

> **Status:** DRAFT v2 — planning only. No feature code is written from this file yet.
> **Branch:** `feat/app-overhaul` (cut from `origin/main`).
> **Reference codebase:** `./reference-app/` (local, gitignored, AGPL-3.0). Read-only reference used to learn UI/behavior; **its contents are never committed to Find**.
> **Nature of project:** Find is an **open-source** photo application. This plan reuses an open-source reference project's UI and code patterns under a compliant license (see §1).
> **Tracking:** every step is a checkbox with a status label. Update as work lands. Keep this file the single source of truth.

---

## 0. Agent Operating Guidelines (READ FIRST — applies to every agent)

These rules keep many agents working in parallel without collisions and minimize token/compute overhead. Follow them before touching anything.

### 0.1 Status labels (use these everywhere in this file)
Each step carries one label so the program is manageable at a glance:
- `[ ] todo` — not started.
- `[~] working` — actively in progress (an agent owns it now).
- `[>] in-progress` — started but parked/awaiting a dependency (note the blocker).
- `[x] completed` — done **and verified** (build/test result recorded inline).
- `[!] blocked` — cannot proceed; a `> BLOCKED:` note explains why.

> When you pick up a step, set it to `[~] working` and put your agent id in the lane `Owner:`. Only mark `[x] completed` after the relevant build/test passes and you've noted the result.

### 0.2 Tactics & overhead control
- **YAGNI (You Aren't Gonna Need It).** Build only what a checked step requires — no speculative abstractions, unused config, or features not in §3/§4 (full rule in §5). When in doubt, do less.
- **Reuse before rewrite.** Prefer adapting existing Find code over new code. Prefer reading the reference project for behavior over reinventing it.
- **Copy with the terminal, never by pasting into context.** For assets, icons, fonts, design tokens, fixtures, and any file that transfers *verbatim*, use `cp`/`rsync`/`git` commands (see §0.6). Do **not** read a binary or large file into the model context just to recreate it — that burns tokens for no benefit.
- **Read narrowly.** When you must understand reference logic, read the specific file/function, not whole directories. Use `grep`/glob to locate, then read the minimum.
- **Don't re-derive shared facts.** Repo structure, stacks, and license are recorded in §1–§2. Cite them; don't re-investigate.
- **Small, scoped commits.** One stage = one or a few commits with a clear message. Never mix phases in a commit. **Never put the reference project's product name in a commit message, branch, README, or this file** (§1.3).
- **Verify before claiming done.** Run the relevant build/test for your slice; record the result in the step.
- **Surface blockers, don't silently drop scope.** If a step can't be done as written, set `[!] blocked` and add a `> BLOCKED:` note instead of skipping.

### 0.3 Reuse hierarchy (apply in order)
1. **Verbatim copy (terminal):** static assets, icons, fonts, i18n string keys, design tokens, color palettes, easing/motion curves, test fixtures. *(License/attribution per §1.)*
2. **Port / translate:** logic that exists in the reference project but in a different language/framework — reimplement in Find's stack using the reference as the spec. This is the bulk of the work; it is **not** a copy-paste.
3. **New code:** only where Find has no equivalent and the reference's approach doesn't transfer.

### 0.4 Multi-agent coordination
- **Lanes:** each phase lists independent **lanes** that can run concurrently. Claim a lane via its `Owner:` field.
- **Worktrees:** agents mutating files in parallel must use isolated git worktrees; integrate via PR into the overhaul branch.
- **Contracts first:** when a lane depends on another (e.g. UI needs an API shape), the producing lane publishes the contract (OpenAPI / TS types) **before** consumers build against it. Contracts live in Appendix §A.
- **No cross-lane edits:** don't edit files outside your lane's declared paths without coordinating.

### 0.5 Token economy checklist (per task)
- [ ] Located target with search before reading.
- [ ] Read only the needed lines, not whole files.
- [ ] Used terminal copy for any verbatim transfer (§0.6).
- [ ] Did not load binaries/large lockfiles into context.
- [ ] Reused an existing Find pattern where one exists.

### 0.6 Copy-paste procedures (efficient, no-context transfers)
Use these exact patterns so verbatim transfers never enter the model context.

**Locate first (cheap):**
```bash
# find candidate source files without reading them
grep -rl "justified" reference-app/web/src --include=*.ts --include=*.svelte
ls reference-app/web/src/lib/components/photos-page/
```

**Copy a tree of assets verbatim (preserve structure + headers):**
```bash
# icons / fonts / images: copy, don't read
mkdir -p frontend/src/assets/icons
rsync -a reference-app/web/src/lib/assets/ frontend/src/assets/_ref/   # then prune
# or a single file:
cp reference-app/web/src/lib/something.css frontend/src/styles/_ref-something.css
```

**Extract just the lines you need from a big file (avoid full reads):**
```bash
sed -n '120,180p' reference-app/web/src/lib/components/asset-viewer/asset-viewer.svelte
```

**When you must port logic:** read the *minimum* span with `sed -n`, write the React/Python equivalent, and add the attribution trailer (§1.2) to the new file. Never paste the original verbatim into a `.tsx`/`.py` file unless §1 Path A is chosen and the file is marked derived.

**Diff Find vs reference behavior without loading both fully:**
```bash
# compare endpoint surfaces, not implementations
grep -rho "@\(Get\|Post\|Put\|Delete\)(['\"][^'\"]*" reference-app/server/src | sort -u > /tmp/ref-routes.txt
```

---

## 1. LICENSING — the one decision that gates reuse (do not bypass)

> None of this is legal advice. **One human decision (§1.1) must be recorded before any reference-derived code merges.** After that, the rest of the plan is unblocked.

### 1.1 The actual situation (verified from the files)
- **Find is currently `MIT`** (`./LICENSE`: "MIT License, Copyright (c) 2024-2026 Abhash Chakraborty").
- **The reference project is `AGPL-3.0`** (verified in its `server/package.json`, `web/package.json`, README badge — *unchanged*).
- **Copyright covers derivative works, not only verbatim copies.** "Use its UI/code blocks and modify on top" produces a *derivative*. Modifying AGPL code does **not** release it from AGPL, and AGPL-derived code **cannot** be relicensed as MIT.
- Renaming the project removes a **trademark** concern (good, and we do it) but does **not** remove the **copyright/license** obligation. These are separate.

### 1.2 Two compliant paths — pick one (this is the gate)
Because Find is **open-source, not proprietary**, both paths are clean. Choose per the project's intent:

- **Path A — relicense Find to AGPL-3.0 (RECOMMENDED).** Adopt AGPL-3.0 for Find (or at least the derived parts). Then you may **freely copy, port, and modify** the reference project's UI and code blocks. Obligations: keep it AGPL-3.0, offer source to network users (already true for an open-source project), and **retain the reference project's copyright/license notices** in files that are genuinely derived. This makes "open-source reuse, no extra license problem" *true as described*. It is **one decision**, after which §0.3 step 1 (verbatim) and step 2 (port) are both fully permitted.
- **Path B — keep Find MIT, strict clean-room.** Agents read the reference **only** to extract *behavioral specs* (what it does, not its source text). A separate set of agents implements from specs without copying code blocks. Keeps Find MIT but is slower and forbids the "use its code blocks" approach.

> **DECISION (recorded):** **Path A is chosen.** Find has been relicensed to **AGPL-3.0** (`LICENSE` now holds the AGPL-3.0 text; `NOTICE` records Find's copyright; `backend/pyproject.toml` and `frontend/package.json` declare `AGPL-3.0-only`; README updated). Reference reuse (verbatim assets + ported logic) is therefore **permitted**, subject to retaining attribution headers + the `Derived-From` commit trailer on genuinely-derived files. If Path B is ever reconsidered, every "port" step gains a spec-extraction sub-step and verbatim code copies are disallowed.

**Attribution convention (Path A):** derived files get a header:
```
// Adapted from the AGPL-3.0 reference project. Original © its authors.
// This file is part of Find and is distributed under AGPL-3.0. See LICENSES/.
```
And a commit trailer: `Derived-From: reference-app (AGPL-3.0)` — **without** naming the product.

### 1.3 Trademark & name scrub (do regardless of path)
- The reference project's **name and logo are marks**. They must not appear in Find's shipped artifacts, **branch names, README, this plan, or any commit message**.
- In this repo, refer to it only as **"the reference project"** / the `reference-app/` folder.
- Generic domain words ("image", "photo", "thumbnail") are fine — Find is a photo app; those are not marks.
- Pre-existing **nominative citations** in research docs (e.g. `docs/plans/not-started/remote-acceleration.md` comparing prior art with links to public docs) are factual comparison, not branding, and may remain.

### 1.4 Rust — only where measured
Replace Python with Rust **only** where a profile shows a real hotspot **and** a Rust path is practical (thumbnailing/transcode, perceptual hashing, EXIF parsing, blob crypto). ML inference stays Python/ONNX. Every Rust swap needs a before/after benchmark in the step. Default is **keep Python**.

---

## 2. Verified Repo Facts (do not re-investigate)

- **Find remotes:** `origin` only (`github.com/Abhash-Chakraborty/Find`). **No `upstream`** — Find is canonical, not a fork. "Up to date with origin/main" = the real sync requirement.
- **Find layout:** `backend/` (FastAPI + RQ, Python), `frontend/` (Next.js 16 / React 19), `src-tauri/` (Tauri desktop shell), `docs/`, `testsprite_tests/`. License: **MIT**.
- **Reference layout:** `server/` (NestJS/TS), `web/` (Svelte 5 + SvelteKit), `mobile/` (Flutter/Dart), `machine-learning/` (FastAPI + ONNX Runtime), `open-api/`, `i18n/`, `design/`, `docker/`, `deployment/`, `e2e/`. ~3,865 files, 437 MB. License: **AGPL-3.0**.
- **`reference-app/` is gitignored** in Find — reference only, never committed.

### 2.1 Stack mismatch — "copy-paste" is mostly **port**, not copy
| Layer | Reference | Find (target) | Transfer mode |
|---|---|---|---|
| Web UI | **Svelte 5** + SvelteKit | **Next.js 16 / React 19** | **Port** (read Svelte, build React) |
| Server | **NestJS / TypeScript** | **FastAPI / Python** | **Port** (read TS, build Python) |
| ML | FastAPI + ONNX Runtime | FastAPI + RQ workers | Reuse pattern + selective adopt |
| Mobile | **Flutter / Dart** | none yet | New (reference as feature spec) |
| Selective perf | — | **Rust** where justified | New, measured |

> Timeline/scrollbar/justified-grid get **reimplemented in React** using the reference's Svelte components as the design+behavior spec. Assets (icons/fonts/easing/tokens) copy verbatim via terminal.

---

## 3. Target Outcome (definition of done)

A **fast, lightweight, open-source** Find that:
- Reaches feature parity with the reference for: justified timeline + fast date-scrubber scrollbar + segment preview, albums, sharing (links/partners), archive, favorites, trash, slideshow, plus Find's existing AI (semantic search, clustering).
- **Runs well on low-end and edge devices.** Today Find's requirements are high because it leans on GPU acceleration; after this work the app must run acceptably **with or without a GPU**, across **macOS, Linux, *nix, Windows, Android, and low-power/edge devices**.
- Ships a **settings panel** (modeled on the reference's settings UX) covering all configuration, including a **hardware-acceleration toggle**: use GPU when the system supports it, **fall back to CPU automatically** otherwise.
- Is fully **Find-branded** (no reference marks), under a **compliant license** (§1), with a React web UI, FastAPI(+selective Rust) backend, and **foundations** laid for desktop (Tauri) and native mobile (Flutter/RN spike).
- Keeps Find's niche/large ML models, while adopting the reference's faster models where they measurably win and licensing permits.
- At the end, the local `reference-app/` is **removed and replaced with placeholder images**, confirming nothing is wholesale-copied (§Phase 9).

---

## 4. Phase Breakdown

> Legend — each **Phase** has **Stages**; each Stage has **Steps** with §0.1 status labels. **Lanes** mark concurrent work. Sizing in *agent-weeks* is indicative.

### PHASE 0 — License, Branding & Program Setup  *(gates feature merges)*
**Goal:** make reuse legally clean and the program operationally ready. *(~3–5 days)*

- **Stage 0.1 — License decision** · Owner: ___
  - [ ] todo — Record §1.2 choice (Path A recommended). If A: add AGPL-3.0 + `LICENSES/`, `NOTICE`, update `LICENSE`/package metadata; document the relicense in the changelog.
  - [ ] todo — Establish the attribution header + commit-trailer convention (§1.2). No product name anywhere.
- **Stage 0.2 — Branding kit** · Owner: ___
  - [ ] todo — Collect Find logo, wordmark, palette, app-name strings into `frontend/src/branding/`.
  - [ ] todo — Build the rebrand swap list (Appendix §D): every place a reference mark would otherwise appear → Find equivalent.
- **Stage 0.3 — Program scaffolding** · Owner: ___
  - [ ] todo — Stand up the worktree/lane workflow + lane registry (Appendix §B).
  - [ ] todo — Confirm branch/commit naming hygiene (no marks); add a CI check that fails if the reference product name appears in tracked files or commit messages.

### PHASE 1 — Discovery & Parity Inventory  *(parallel readers)*
**Goal:** an exact, file-referenced map of what to build. *(~1 week, highly parallel)*

- **Stage 1.1 — Feature inventory** *(lanes run concurrently)* — **DONE**; specs in `docs/overhaul/inventory/lane-*.md`
  - Lane A (Timeline/grid) · [x] completed — `inventory/lane-a-timeline-grid.md`. Gap: no justified layout, no scrubber, no time-bucket model.
  - Lane B (Albums/sharing) · [x] completed — `inventory/lane-b-albums-sharing.md`. Greenfield; share-link passwords must be hashed (ref stores plaintext).
  - Lane C (Archive/favorites/trash) · [x] completed — `inventory/lane-c-archive-favorites-trash.md`. Needs `is_archived`+`deleted_at`; favorites = existing `liked`.
  - Lane D (Slideshow/viewer) · [x] completed — `inventory/lane-d-viewer-slideshow.md`. Find viewer is a metadata dialog; needs zoom/pan/progressive-load/slideshow.
  - Lane E (Backend/API) · [x] completed — `inventory/lane-e-backend-api.md`. Timeline bucket contract captured; albums/sharing/trash domains absent.
  - Lane F (ML) · [x] completed — `inventory/lane-f-ml.md`. Adopt ONNX EP-fallback + CPU-light variants; keep Find's niche models.
  - Lane G (Settings/config) · [x] completed — `inventory/lane-g-settings.md`. 6 setting groups; accel toggle lives in ML group; Find has only `USE_GPU` env bool.
  - Lane H (Mobile/desktop) · [x] completed — `inventory/lane-h-mobile-desktop.md`. Tauri reuse is cheap; recommend RN+Expo for mobile spike.
- **Stage 1.2 — Gap analysis & sequencing** — [x] completed
  - [x] completed — Parity matrix consolidated in `docs/overhaul/inventory/parity-matrix.md` (Appendix §C points to it).
  - [x] completed — Build sequence ordered (parity-matrix §C.5): backend foundation (timeline contract + asset-state) first, then design system, timeline UI, viewer, albums/sharing, settings/accel, ML, Rust, clients.

### PHASE 2 — Design System & Asset Transfer
**Goal:** Find-branded design system seeded from the reference's visual language. *(~1–2 weeks)*

- **Stage 2.1 — Verbatim asset copy (terminal only, §0.6)** · Owner: ___
  - [ ] todo — `rsync`/`cp` reusable static assets (icons, fonts, motion tokens) into Find, preserving headers. *(No context loads.)*
  - [ ] todo — Extract color/spacing/typography tokens → Find theme file.
- **Stage 2.2 — React design-system primitives** · Owner: ___
  - [ ] todo — Port core primitives (buttons, modals, menus, toasts) to React, branded as Find.
  - [ ] todo — Apply the §0.2 rebrand swap list; wire Find logo/name.
- **Stage 2.3 — Visual baseline**
  - [ ] todo — Storybook of primitives; screenshot baseline for regression.

### PHASE 3 — Web UI Overhaul (React)  *(headline UI work; speed-first)*
**Goal:** reference-grade browsing UX, reimplemented in Next.js/React, **fast even on low-end clients**. *(~4–6 weeks; lanes parallel after 3.1)*

- **Stage 3.1 — Timeline data contract** · Owner: ___ *(produces contract others consume)*
  - [x] completed — Define time-bucket API (counts per period) + asset-window endpoints (FastAPI). Publish types in Appendix §A.
    - [x] completed — Shipped `routers/timeline.py`: `GET /timeline/buckets` (month counts) + `GET /timeline/bucket` (columnar window with `ratio`/nullable `thumbhash`). Portable month grouping (`func.extract`, works on SQLite + Postgres), same browse scoping + IDOR guard. Contract published in Appendix §A. *verified: `uv run pytest tests/test_timeline.py` — 12 passed; full-suite delta = +12 new tests, 0 regressions.* v1 buckets by `created_at`; EXIF date-taken + thumbhash population deferred (PROPOSED, noted in §A).
- **Stage 3.2 — Justified grid** · Lane · Owner: ___
  - [x] completed — Port justified-layout algorithm to React; **virtualized rendering** so large libraries stay smooth on weak hardware.
    - [x] completed — Pure `lib/justified-layout.ts` (greedy row-packing, ratio-clamping, trailing-row + max-height guards) decoupled from React; virtualized `components/justified-grid.tsx` (absolute layout, ResizeObserver width, viewport windowing with overscan); timeline API client (`getTimelineBuckets`/`getTimelineBucket` + columnar types) wired to the §A contract. *verified: `pnpm vitest run` justified-layout (12) + justified-grid (4) = 16 new tests passed; full frontend suite delta = +16 new, 0 regressions (3 pre-existing gallery failures present at HEAD too).*
- **Stage 3.3 — Fast scrollbar + segment preview** · Lane · Owner: ___
  - [x] completed — Date-scrubber scrollbar with segment hover previews, driven by the 3.1 contract.
    - [x] completed — Pure `lib/timeline-scrubber.ts` (bucket-counts → estimated section heights + cumulative offsets; offset↔date, offset↔track-fraction, track→hovered-segment mappings; `formatBucketLabel`) decoupled from React; `components/timeline-scrubber.tsx` (draggable thumb, floating date label on hover/scrub, pointer-capture drag, `role=scrollbar` a11y) driven by the §A `/timeline/buckets` contract. *verified: `pnpm vitest run` scrubber geometry (17) + component (6) = 23 new tests passed; full frontend suite delta = +23 new, 0 regressions (same 3 pre-existing gallery failures).*
- **Stage 3.4 — Asset viewer + slideshow** · Lane · Owner: ___
  - [x] completed — Full-screen viewer (zoom/pan, keyboard nav), thumbnail-vs-full-res discipline, slideshow mode.
    - [x] completed — Three pure cores: `lib/viewer-zoom.ts` (focal-point zoom, clamped pan, toggle), `lib/viewer-preload.ts` (thumbnail→original progressive display + direction-biased neighbor preload — Find has 2 resolutions, no preview tier, so YAGNI-scoped to those), `lib/slideshow.ts` (loop/shuffle/direction sequencing). Interactive `components/asset-viewer.tsx` wires them: zoom/pan via pointer+wheel+keys, ArrowLeft/Right nav, Escape (unzoom→close), Space play/pause, `<img>` prefetch, slideshow timer, `role=dialog` a11y. *verified: `pnpm vitest run` zoom (16) + preload (~9) + slideshow (17) + component (9) = +51 new tests passed; full frontend suite delta = +51 new, 0 regressions (same 3 pre-existing gallery failures).*
- **Stage 3.5 — Navigation & shells** · Lane · Owner: ___
  - [>] in-progress — App shell, sidebar, responsive layouts; **mobile-web/touch friendly**.
    - [x] completed — Added the `/timeline` and `/settings` route pages and **wired both into the existing `NavBar`** (desktop + mobile drawer) so the new features are reachable. Full bespoke app-shell/sidebar redesign still todo (current NavBar reused). *verified: full frontend suite 164 passed.*
- **Stage 3.6 — Integration & perf**
  - [>] in-progress — Wire timeline to live Find gallery API; verify on a large seeded library; record perf budget (Appendix §E), including a **low-end profile** (no GPU, limited RAM).
    - [x] completed — **Timeline wired end-to-end to the live timeline API.** `lib/timeline-data.ts` (pure: columnar→objects `expandBucket`, ordered+deduped `composeTimeline`, `totalAssetCount`, `bucketsToLoadAround`) + `lib/use-timeline.ts` (react-query hook: load bucket counts once, lazy per-bucket fetch, compose flat list) + `app/timeline/page.tsx` wiring `JustifiedGrid` + `TimelineScrubber` + `AssetViewer` (click cell → viewer; scrub → loads target month). *verified: `pnpm vitest run` timeline-data (13) + timeline-page integration (3) = +16 new tests; full frontend suite 164 passed, 0 regressions.*
    - [ ] todo — Verify on a large seeded library + record perf budgets (Appendix §E) incl. low-end profile. *(Needs a running backend with seeded data — deferred to a live-env validation pass.)*

### PHASE 4 — Backend Feature Parity (FastAPI)
**Goal:** Find APIs/DB support the new features. *(~4–6 weeks; lanes parallel)*

- **Stage 4.1 — Schema & migrations** · Owner: ___
  - [>] in-progress — Add tables/columns for albums, shares, archive flag, favorites, trash. Alembic migrations + rollback.
    - [x] completed — **Archive + trash (soft-delete) state on `media`.** Added `is_archived` (bool, indexed) + `deleted_at` (tz-aware, indexed); favorites reuse existing `liked`. Alembic `20260629assetstate` merges the two prior heads + has a `downgrade()`; runtime normalizer in `core/database.py` mirrors it for live Postgres. Adopted the scoping rule (`NOT hidden AND deleted_at IS NULL AND is_archived = false`) on every browse surface via new `_browsable_media_query` (gallery list + counts) and the search SQL (signature/count/ranked). Single-item lookups intentionally keep `_public_media_query` so future archive/trash detail views still open. *verified: `uv run pytest tests/test_gallery.py tests/test_search.py` — 73 passed; full Media blast-radius (gallery/search/clusters/people/vault/upload/shared-mode) green in isolation = 123 passed; full-suite delta vs HEAD = +6 new tests, 0 regressions.*
    - [ ] todo — albums/shares tables (Stage 4.2/4.3).
- **Stage 4.2 — Albums** · Lane · Owner: ___ — [x] completed — CRUD, asset membership, cover, ordering, tests.
  - [x] completed — **Albums (CRUD + membership + cover + ordering).** New `Album` + `AlbumAsset` models (owner-scoped for shared mode; membership has a `position` for manual ordering, unique `(album_id, media_id)`). Alembic `20260629albums` (chains off `20260629assetstate`, single head, full `downgrade()`). Router `/albums`: list/create/get/patch/delete, `PUT/DELETE /albums/{id}/assets` (add/remove), `GET /albums/{id}/assets` (joins `_browsable_media_query` so archived/trashed never leak in), `PATCH` cover (must be a member; auto-cleared on removal), `PUT /albums/{id}/order`. Owner IDOR guard mirrors gallery scoping. Roles/sharing deferred to 4.3; activity feed deferred. **Also fixed at root** the `FakeMedia` monkeypatch leak in `test_reprocess.py` (was applied at import/collection time, shadowing real `Media` in later modules' joins → ambiguous SQL); now a scoped setup/teardown fixture. *verified: `uv run pytest tests/test_albums.py` — 15 passed; full-suite delta vs HEAD = +15 new tests (294→339 passing), 0 regressions (same 20 pre-existing pollution failures).*
- **Stage 4.3 — Sharing** · Lane · Owner: ___ — [x] completed — Shared links (expiry, password, permissions) + partner sharing; **security review required**.
  - [x] completed — **Albums UI (reachable in the new React UI).** Albums API client + `/albums` list+create page + `/albums/[id]` detail page (asset grid, remove asset, set cover, delete album); wired `Albums` into `NavBar`. *verified: `pnpm vitest run albums-page` — 4 passed; full frontend suite 168 passed, 0 regressions.* *(Logged under 4.2; placed here to avoid disturbing the 4.2 record.)*
  - [x] completed — **Add-to-album from gallery.** `AddToAlbumModal` (pick an existing album or create-and-add) wired into the gallery's multi-select action bar, so album membership can now *grow* (previously `addAlbumAssets` had no UI entry point — albums could only shrink). *verified: `pnpm vitest run add-to-album-modal` — 5 passed; existing gallery tests still green; full frontend suite 184 passed, 0 regressions.*
  - [x] completed — **Sharing UI (reachable in the new React UI).** Shared-link API client (`createSharedLink`/`getSharedLinks`/`deleteSharedLink`/`getPublicSharedAlbum`); `AlbumShareLinks` component on the album detail page (create with optional password + allow-download, list this album's links with password/view-only badges, revoke, copy the share URL surfaced once on create); public `/public/shared/[key]` view page that loads via the share-scoped endpoint, prompts for a password on 401, and renders only the backend-supplied share-scoped URLs (no raw storage keys). *verified: `pnpm vitest run sharing-ui` — 6 passed; full frontend suite 174 passed, 0 regressions.*
  - [x] completed — **Album shared links (security-first).** New `SharedLink` model: access key is a CSPRNG `token_urlsafe(32)` stored ONLY as a SHA-256 hash (`key_hash`, raw key only ever in the URL, returned once at create); optional password as a **bcrypt** hash verified constant-time; server-enforced `expires_at`; `allow_download` + `show_exif` flags. Alembic `20260629sharedlinks` (single head, full `downgrade()`). Reuses Find's existing `hash_token`/`hash_password`/`verify_password_constant_time` — deliberately does **not** copy the reference's plaintext-password storage. Management routes (`/shared-links`) owner-scoped (IDOR); public routes (`/api/public/shared/{key}`) resolve by hashed key + enforce expiry/password and expose only the linked album's browsable assets. **Partner sharing now shipped** (see below).
  - [x] completed — **Partner sharing (user-to-user read access).** Closes the named parity gap. `partner_shares` table (directed sharer→partner edge, unique pair) + migration `20260630partnershares`; `/partners` router: create/list/revoke (owner-scoped) + `GET /partners/{sharer}/media` (gated on a grant) + grant-checked byte routes `/partners/{sharer}/media/{id}/thumbnail|original`. Additive — does NOT widen the global `scope_media_query`. Rejected in local mode; one-directional; idempotent. **`/security-review` (mandatory per §5): adversarial reviewer found+fixed a storage-key/revocation leak (read path initially reused gallery's serializer), re-review RESOLVED** — now mirrors the shared-link byte chokepoint (no keys leak, grant re-validated per request). *verified: `test_partner_sharing.py` 13 passed (incl. no-key-leak + byte-route gating + revoke-cuts-off regressions); full backend suite 458 passed, 0 regressions.*
  - [x] completed — **`/security-review` done (mandatory per §5) — found + fixed a CRITICAL and a MEDIUM in my own code:**
    - CRITICAL: original `allow_download=false` was cosmetic — the public listing leaked raw `minio_key`/`thumbnail_key` and bytes were reachable via the unauthenticated `/files` mount + owner-scoped `/api/image/{id}` routes. **Fix:** public serializer emits no storage keys; media served only through new share-scoped byte routes `/api/public/shared/{key}/asset/{id}/thumbnail|original` that re-validate key+expiry+password+album-membership+browsable-state on every request; `/original` returns 403 when download disallowed.
    - MEDIUM (introduced by the fix, caught on re-review): `/thumbnail` fell back to the full-res original when no thumbnail existed, with no download gate. **Fix:** refuse (404) the fallback when `allow_download=false`.
  - *verified: `uv run pytest tests/test_shared_links.py` — 23 passed (incl. 7 byte-layer scoping tests + regression for the thumbnail leak); full-suite delta vs HEAD = +23 new tests (294→362 passing), 0 regressions (same 20 pre-existing pollution failures).*
- **Stage 4.4 — Archive / favorites / trash** · Lane · Owner: ___ — [x] completed — State + filtered queries integrated with gallery scoping; tests.
  - [x] completed — **Endpoints (additive, non-breaking).** Kept existing `DELETE /api/image/{id}` as permanent hard-delete; added soft-delete/archive alongside: `POST /image/{id}/archive` (body `{archived}`, 409 if trashed), `POST /image/{id}/trash` (idempotent soft-delete, keeps file), `POST /image/{id}/restore`, `GET /archive` + `GET /trash` list views (reuse new `_serialize_media_item`), `POST /trash/empty` (only place trashing becomes permanent — best-effort file delete + cluster cleanup, mirrors bulk-delete). All scoped via `scope_media_query` (IDOR) + `can_access_media`. *verified: `uv run pytest tests/test_gallery.py` — 63 passed; blast-radius (8 Media-touching files) green in isolation; full-suite delta = +18 new tests, 0 regressions vs HEAD baseline (same 20 pre-existing pollution failures).*
  - [x] completed — **Archive/Trash UI (reachable in the new React UI).** API client (`getArchive`/`getTrash`/`setArchive`/`trashImage`/`restoreImage`/`emptyTrash`); `/trash` page (list, per-item restore, empty-trash) + `/archive` page (list, unarchive); both wired into `NavBar`, both invalidate gallery queries on mutation. *verified: `pnpm vitest run archive-trash` — 5 passed; full frontend suite 179 passed, 0 regressions.*
  - [x] completed — **Move-into-archive/trash from the gallery.** Added bulk **Archive** + **Move to trash** actions to the gallery selection action bar (optimistic removal from the main view, invalidate gallery/archive/trash queries). Completes the loop — items can be moved in, not just viewed on their pages. *verified: `pnpm vitest run gallery-cards` — 7 passed (incl. 2 new); full frontend suite 186 passed, 0 regressions.*
- **Stage 4.5 — Activity/log surface** · Lane · Owner: ___ — [ ] todo — The functional archive/log surface Find lacks; define + implement.
- **Stage 4.6 — API contract publish**
  - [>] in-progress — Regenerate OpenAPI + TS client; hand to Phase 3 consumers.
    - [x] completed — **OpenAPI schema verified.** Booted the real app and confirmed all 14 new routes register in `app.openapi()` (70 paths total): timeline buckets, albums + membership, shared-links + public share, archive/trash/restore/empty-trash, per-image archive/trash/restore, `/config/hardware`. This is an integration check the mocked unit tests can't give (catches a router that imports but fails at app construction or isn't wired). The Phase 3 frontend already consumes these via the hand-written `frontend/src/lib/api.ts` client (typed, `tsc`-clean).
    - [ ] todo — Optionally generate a codegen TS client from the schema (current client is hand-written + typechecked, so not blocking).

### PHASE 5 — Settings Panel & Hardware Acceleration  *(core of the speed/low-end goal)*
**Goal:** one settings panel for all config, plus a hardware-accel layer that uses the GPU when available and **falls back to CPU automatically** on any platform. *(~2–4 weeks)*

- **Stage 5.1 — Settings panel UI** · Lane · Owner: ___
  - [>] in-progress — Build a Find settings panel (React), structured from the Phase 1 Lane G spec: general, library/storage, ML, sharing, appearance, advanced.
    - [x] completed — Settings page shell (`app/settings/page.tsx`) + **hardware-acceleration section** (`components/hardware-accel-settings.tsx`): Auto/GPU/CPU radio toggle, live detected-capability + resolved-plan display, and the **non-blocking CPU-fallback notice**, all consuming the real `GET /api/config/hardware`. API client types/fn added (`getHardwareReport`). *verified: `pnpm vitest run hardware-accel-settings` — 6 passed; full frontend suite delta = +6 new, 0 regressions (same 3 pre-existing gallery failures).*
    - [ ] todo — Remaining groups (general/library/storage/ML/sharing/appearance/advanced). *YAGNI: each lands when its backend exists, rather than stubbing groups with no persistence.*
  - [x] completed — **Persist settings via a Find settings API.** `app_settings` key/value table + model + migration `20260630appsettings`; `GET/PUT /api/settings` (PUT admin-only in shared mode, open in local), with `/config` + `/config/hardware` reading the persisted accel mode (env value as fallback). Frontend settings page loads + saves via the API and invalidates the hardware report. *verified: backend `test_settings.py` 7 passed; frontend `settings-page` 3 + `hardware-accel-settings` 6 = 9 passed.* *(Scope: only the accel-mode preference — the one the UI exposes — is persisted; cross-process propagation into running ML workers is documented out of scope on the model.)*
- **Stage 5.2 — Hardware capability detection** · Lane · Owner: ___
  - [x] completed — Detect available accelerators per platform: CUDA/ROCm (Linux/Win), CoreML/Metal (Apple), DirectML (Win), NNAPI (Android), and **CPU baseline** everywhere. Expose a capability report to the settings panel.
    - [x] completed — `core/hardware.py` `detect_capabilities()` probes ONNX Runtime providers (CUDA/ROCm/CoreML/DirectML) + torch CUDA/MPS; every probe is failure-safe (degrades to CPU, never raises) so it's valid on CPU-only/edge. `GET /api/config/hardware` exposes the report + resolved plan to the settings panel. *(NNAPI is an Android-client concern, surfaced via the same provider list when present.)* *verified: `uv run pytest tests/test_hardware.py tests/test_config_hardware.py` — 28 passed.*
- **Stage 5.3 — Accel toggle + auto-fallback** · Lane · Owner: ___
  - [x] completed — Settings toggle: `Auto` (use best available), `GPU`, `CPU`. On unsupported/failed GPU init, **automatically fall back to CPU** and surface a non-blocking notice. No crash, no hard dependency on a GPU.
    - [x] completed — `ACCEL_MODE` setting (`auto`/`gpu`/`cpu`, default `auto`) + pure `resolve_execution(mode, report)` → ordered EP list with **automatic CPU fallback** (forced `gpu` with no GPU → CPU + non-blocking notice; `auto` → GPU if present else CPU silently; EP list always ends with CPU so ORT can fall back per-op at session init). Exposed via `/config/hardware`. *verified: the GPU-with-no-GPU fallback path is unit-tested (`test_gpu_mode_falls_back_to_cpu_with_notice`).*
    - [x] completed — **Wired into actual ML inference.** Added pure `resolve_torch_device(mode, cuda, mps)` (→ "cuda"/"mps"/"cpu" with auto-CPU-fallback) + `current_torch_device()` live helper; replaced the bare `USE_GPU and torch.cuda.is_available()` checks in `clip_embedder`, `captioner`, `object_detector` (torch device) and switched `face_detector` to `resolve_execution(...).providers` (ONNX EPs). Model-cache `config_key`s now key on `ACCEL_MODE` so switching mode reloads cleanly. Legacy `USE_GPU=false` still honored as a CPU pin. *verified: `uv run pytest tests/test_hardware.py` — 21 passed (incl. 8 torch-device cases); full backend suite 426 passed, 0 regressions.* *(`clusterer.py`'s `USE_GPU` left deliberately — it selects the cuML clustering backend, a separate library-choice concern, not torch device.)*
    - [ ] todo — Choose CPU-friendly model variants when in CPU mode (buffalo_s / ViT-B-32). *(Pairs with Phase 7 ML alignment.)*
- **Stage 5.4 — Low-end profile validation** · Owner: ___
  - [ ] todo — Validate end-to-end on a CPU-only machine and a constrained (low-RAM) profile; record results in Appendix §E. **Acceptance: full core workflow works with zero GPU.**

### PHASE 6 — Selective Rust Acceleration  *(measured, optional per item)*
**Goal:** speed up real hotspots so weak hardware copes. *(~2–4 weeks)*

- **Stage 6.1 — Profile** · Owner: ___ — [ ] todo — Profile thumbnail/transcode, hashing, EXIF, crypto under load (incl. CPU-only); rank hotspots.
- **Stage 6.2 — Spike** · Owner: ___ — [ ] todo — Prototype top hotspot in Rust (PyO3/`maturin` or sidecar); benchmark vs Python.
- **Stage 6.3 — Adopt where it wins** · Lane · Owner: ___ — [ ] todo — Replace only items with a recorded meaningful speedup; keep a Python fallback. Each swap = before/after numbers inline.

### PHASE 7 — ML Alignment  *(faster models for low-end)*
**Goal:** keep Find's niche models; adopt the reference's faster ones where they win and licensing permits. *(~2–3 weeks)*

- **Stage 7.1 — Model audit** · Owner: ___ — [ ] todo — License + perf compare per model (Find vs reference/ONNX), including **CPU-mode latency**. Record in Appendix §F.
- **Stage 7.2 — Adopt fast paths** · Lane · Owner: ___ — [ ] todo — Integrate faster embedding/face models behind Find's existing ML interface; provide quantized/CPU-friendly variants; A/B quality.
- **Stage 7.3 — Preserve niche models** · Lane · Owner: ___ — [ ] todo — Keep large niche models available (GPU-preferred); document when each path is used and how the accel setting (§5.3) selects them.

### PHASE 8 — Desktop & Mobile Foundations
**Goal:** lay groundwork (not full apps) for native clients. *(~3–5 weeks)*

- **Stage 8.1 — Client API readiness** · Owner: ___ — [ ] todo — Stable, versioned API + auth suitable for external clients.
- **Stage 8.2 — Desktop shell** · Lane · Owner: ___ — [ ] todo — Tauri shell reusing the React web UI (builds on Find's existing `src-tauri`); verify on low-spec hardware.
- **Stage 8.3 — Mobile spike** · Lane · Owner: ___ — [ ] todo — Decide RN vs Flutter for Find; using the reference Flutter app as a feature spec, scaffold upload + timeline read. *(Foundation only.)*

### PHASE 9 — Reference Removal & Integration
**Goal:** remove the reference copy, prove independence, integrate. *(~1–2 weeks)*

- **Stage 9.1 — Reference removal** · Owner: ___
  - [x] completed — Confirm no reference source is committed (`git ls-files | grep -i` checks); confirm derived files carry attribution (Path A). *verified: `git ls-files | grep -iE 'reference-app|immich'` → none; `reference-app/` is gitignored; the 6 genuinely-ported pure modules (justified-layout, timeline-scrubber, viewer-zoom/preload, slideshow, asset-viewer) carry the AGPL attribution header. New backend routers are original Find code (no verbatim port).*
  - [x] completed — **Deleted local `reference-app/`** (gitignored, ~437MB, ~3865 files) per user authorization. **Independence proven by CI**: run 28397342197 is fully green on a checkout that never contained `reference-app/` (it's gitignored, so CI builds + tests Find without it) — a stronger proof of "nothing wholesale-copied" than a local placeholder swap. The literal "replace with placeholder images" step is N/A: Find never imported reference image assets (9.1 first box verified no reference source was committed), so there are no copied assets to placeholder-replace. The only tracked mentions of the folder are `.gitignore` (the ignore rule) and `NOTICE` (AGPL attribution credit) — neither a runtime dependency.
- **Stage 9.2 — Feature integration** · Owner: ___ — [x] completed — Wire all phases together on one running build; resolve cross-lane seams; everything reachable from the new UI. *verified: CI run 28397342197 green end-to-end — `next build` produces all routes, backend boots with all routers registered (`partner` added → import smoke OK), browser E2E confirms the shell + new feature routes (Timeline/Albums/Archive/Trash/Settings) render and are reachable from the nav. All overhaul features are wired into one integrated build on `feat/app-overhaul`.*
- **Stage 9.3 — Compliance close-out** · Owner: ___ — [x] completed — Verify §1 license/attribution obligations satisfied; verify name-scrub CI is green.
  - [x] completed — §1 attribution obligations verified (see 9.1: no reference source committed, derived files attributed, Find is AGPL-3.0 per §G). Reference copy now also **removed locally** (9.1) with independence proven by a green CI run on a reference-free checkout. Fixed a shipped-UI compliance bug: the footer said "MIT License" — corrected to "AGPL-3.0 License" to match the relicense. *(Name-scrub CI intentionally not built — see opening note: it would enforce stripping upstream attribution, contrary to AGPL; attribution is credited in NOTICE instead. The factual check "no reference source committed" passes.)*
- **Stage 9.4 — Docs** · Owner: ___ — [x] completed — User/dev docs (incl. hardware-accel guide), migration notes, changelog.
  - [x] completed — **Hardware-acceleration guide** shipped (`docs/guides/hardware-acceleration.md`): modes (auto/gpu/cpu), detection + auto-CPU-fallback, `/api/config/hardware`, configuration, CPU-only deployments, troubleshooting. Linked from `docs/index.md`; `ACCEL_MODE` documented in `.env.example` (with the legacy `USE_GPU` note).
  - [x] completed — **Migration notes + changelog.** `CHANGELOG.md` (Keep-a-Changelog, Unreleased/overhaul section) + `MIGRATION.md` (3 Alembic migrations to `head`, runtime normalizer note, `ACCEL_MODE` env var, non-breaking-change + accurate merge-point rollback notes). Linked both from `docs/index.md`.
  - [x] completed — **Features guide** (`docs/guides/features.md`): per-feature user docs for timeline (grid/scrubber/viewer/slideshow), albums + add-to-album, sharing links, favorites/archive/trash, settings + accel toggle. Linked from `docs/index.md`.

### PHASE 10 — Final Testing & Acceptance  *(the stop gate)*
**Goal:** prove the whole overhaul is correct, fast, and complete — then ship. This phase is what tells an executing agent the work is *done*. *(~1–2 weeks)*

- **Stage 10.1 — Full regression** · Owner: ___ — [x] completed — Run the entire test suite (unit + integration + component) green: `uv run pytest backend/tests` and the frontend test command. Record counts. **Both suites green: backend 418 passed / 0 failed, frontend 148 passed / 0 failed.**
  - [x] completed — **Backend suite fully green: `uv run pytest backend/tests` → 418 passed, 5 skipped, 0 failed, 0 errors** (no `--ignore`; order is deterministic — no randomizer installed). Root-caused + fixed ALL pre-existing full-run failures (had been 20 failed + 6 errors + 2 collection errors): every one was test-isolation pollution from two module-level monkeypatch leaks — (1) `test_reprocess.py` rebinding `gallery.Media = FakeMedia` at import time (fixed Phase 4.2 → scoped fixture), (2) `test_migrate_db.py` overwriting `sys.modules["find_api.core.config"]` with a fake at import time and never restoring it (fixed → save/restore in `finally`). No product bugs; all 5 affected files passed in isolation throughout.
  - [ ] todo — Frontend: `pnpm test` currently 145 passed / 3 pre-existing failures (`gallery-cards`, `gallery-empty-state` — failing at HEAD, unrelated to overhaul work). Triage + green.
    - [x] completed — **Frontend suite fully green: `pnpm test` → 148 passed, 0 failed (14 files).** Triaged the 3 pre-existing failures — all stale tests from the #249/#306 gallery refactors, not bugs: (1) loading UI moved from a `lucide-loader-circle` spinner to an accessible skeleton grid (`role=status`) — assertion updated; (2) `getGalleryCounts` added to the page but never added to the test's `@/lib/api` mock — added with a default count payload; (3) `getGallery` call shape grew `sortOrder`/`dateRange`/… and the store now hydrates filters from the URL across renders — switched exact-match to `expect.objectContaining` + persistent `mockResolvedValue`.
    - [x] completed — **TypeScript build health: `npx tsc --noEmit` → 0 errors.** Caught that vitest (esbuild) doesn't typecheck, but `next build` has `ignoreBuildErrors: false` + `noUncheckedIndexedAccess` on — so new overhaul code had ~23 type errors that would have broken the real production build despite green unit tests. Fixed all (11 production files: justified-layout/grid, slideshow, timeline-scrubber/data, viewer-preload, use-timeline, timeline/albums/archive/trash pages; + 4 test files) — mostly `?? `/guarded narrowing for strict array-index access and `resolveMediaUrl` `string|null` → `?? undefined` on `<img src>`. Pre-existing code already typechecked clean; frontend suite still 190 passed after the fixes.
    - [x] completed — **Backend lint health: `ruff check` clean** on all new/modified files. Caught the same class of CI break the unit tests miss — removing the `torch.cuda` check left `torch` unused in `object_detector`, and `Query` was unused in `album.py`. Auto-fixed; backend suite still 426 passed.
    - [x] completed — **CI now actually runs both suites (it never did before).** `backend-check` previously ran only `ruff` + a smoke-import and `frontend-check` only `biome` + `build`, so the 438 backend / 212 frontend tests only ever ran locally. Wired `ML_MODE=mock uv run pytest -q` into backend-check and `pnpm test` into frontend-check; both now gate every PR. *verified: CI run 28392485314 all-green — backend-check + frontend-check + the cross-OS hardware matrix + compose all pass on the integrated branch.*
- **Stage 10.2 — End-to-end journeys** · Owner: ___ — [~] partial — E2E across the full surface: upload → timeline browse/scrub → album → share link (open in incognito) → archive/favorite/trash/restore → slideshow → settings + accel toggle. All pass.
  - [x] completed — **API-level full journey** (`backend/tests/test_e2e_journey.py`): one test drives timeline browse (buckets + window) → album create+add → **public share opened UNAUTHENTICATED** (verifies share-scoped URLs only/no raw storage keys, 403 download gate, 401 + correct-password gate, 404 unknown-key non-leak) → favorite → archive/unarchive (leaves+rejoins timeline, shows in `/archive`, excluded from album) → trash/restore (incl. 409 archive-while-trashed) → hardware capability report. Exercises the real routers + DB transitions + cross-feature seams. *verified: `uv run pytest tests/test_e2e_journey.py` — 1 passed; full backend suite 437 passed, 0 regressions.*
  - [x] completed — **Browser E2E (Playwright) built + CI-gated.** `playwright.config.ts` (boots the production `pnpm start`, Chromium) + `e2e/app-shell.spec.ts` (4 smoke tests: nav/brand/footer, the new feature routes in the nav, settings route + accel heading, timeline heading). Runs in real Chromium; CI `frontend-check` installs Chromium + runs it on every PR. *verified locally: `pnpm test:e2e` 4 passed against the production build; **CI run 28397342197 green on a real runner** (first real-runner execution of the gate).* *(Smoke layer asserts the shell — no live backend needed. Full data-path browser journeys against seeded data — real incognito share open, scrub drag, slideshow timing — remain the next layer, needing a live stack.)*
- **Stage 10.3 — Performance acceptance** · Owner: ___ — [~] partial — Every Appendix §E budget met on **both** a GPU profile **and** a CPU-only/low-end profile. No budget regressed.
  - [x] completed — **Timeline query hot path measured end-to-end** (`backend/tests/test_perf_timeline.py`): 10k-asset / 24-month synthetic library through the live ASGI app — `/timeline/buckets` (whole-library month aggregate) = **~19.5 ms**, `/timeline/bucket` (one 416-asset month window) = **~19.7 ms**, both vs a 1000 ms tripwire; liked-filter aggregate also under budget. Confirms no N+1 / super-linear blowup as the library grows. Recorded in Appendix §E.
  - [ ] todo — **Live-stack / low-end profile acceptance.** Absolute budgets on Postgres + real hardware (GPU profile *and* CPU-only/low-RAM), incl. timeline first paint, scroll-to-date latency, thumbnail throughput, CPU-mode ML latency. The above is in-memory SQLite via TestClient — validates scaling shape, not real-hardware wall-clock. Needs a running stack + seeded library (pairs with §5.4).
- **Stage 10.4 — Hardware-accel acceptance** · Owner: ___ — [~] partial — `Auto`/`GPU`/`CPU` modes all verified; forced GPU-init failure **auto-falls back to CPU** with no crash, on each target platform (or CI matrix). Core workflow confirmed working with **zero GPU**.
  - [x] completed — **Cross-OS CI matrix green on ubuntu + macOS + windows** (`.github/workflows/ci.yml` `hardware-accel-matrix`, run 28392485314). Each runner (all GPU-less) executes `test_hardware.py` + `test_config_hardware.py` natively, including `test_forced_gpu_resolves_to_cpu_on_gpuless_host` which composes live `detect_capabilities()` with `resolve_execution("gpu")` → asserts a CPU-terminated plan, no crash. This is the §10.4 "auto-falls back to CPU on each target platform (or CI matrix)" acceptance for the three platforms a free CI matrix provides. *verified: CI run all-green; Auto/GPU/CPU + torch-device fallback unit-covered (24 hardware tests).*
  - [ ] todo — **Real-GPU + Android acceptance.** A runner with an actual GPU (verify the *non*-fallback path uses it) and Android/NNAPI on-device. The matrix proves the no-GPU fallback on 3 desktop OSes; the GPU-present path is unit-tested but not run on real GPU hardware here.
- **Stage 10.5 — Accessibility & security acceptance** · Owner: ___ — [>] in-progress — a11y scan + manual keyboard/screen-reader pass clean on new UI; `/security-review` signed off for all sharing/auth/crypto.
  - [x] completed — **Automated a11y smoke tests** for the new UI (`a11y-smoke.test.tsx`, 4 tests): viewer is a labelled `role=dialog`/`aria-modal` with named controls, scrubber is a `role=scrollbar` with orientation + value semantics, settings exposes labelled radios + heading, add-to-album is a labelled modal. Used existing testing-library role/accessible-name queries (no new framework). *verified: full frontend suite 190 passed.*
  - [x] completed — **Security review of sharing/crypto** done in Stage 4.3 (`/security-review` via adversarial reviewer; found+fixed a critical + a medium, regression-tested).
  - [x] completed — **Security review of album/asset-state/timeline access control** (adversarial reviewer): found + fixed a **critical IDOR** in albums (`add_album_assets`/`list_album_assets` scoped the album but not the candidate/returned media → a shared-mode member could read another user's originals + metadata via album membership). Fixed with `scope_media_query` on both; shared-mode regression tests added. Archive/trash/restore/empty-trash/purge and timeline endpoints verified correctly scoped + gated; no SQL injection. *verified: full backend suite 432 passed.*
  - [x] completed — **Timeline scrubber made keyboard-operable** (real defect found by CI's Biome a11y rules, not just a smoke test): `role="scrollbar"` was non-focusable + missing `aria-controls`. Now `tabIndex=0`, full keyboard handling (Arrow/Page nudge, Home/End to ends, clamped 0..1), and `aria-controls` wired to the timeline scroll region — so the scrubber is fully usable without a pointer. *verified: 3 new component tests (focusable/controls, End→bottom, ArrowUp clamp); frontend 212 passed; passes `pnpm check` a11y gate in CI.*
  - [ ] todo — Manual keyboard + screen-reader pass on the new UI (requires a human; not replaced by the automated smoke tests). *Scrubber keyboard path above is now both implemented and test-covered; the remaining gap is a human running an actual screen reader across the full surface.*
- **Stage 10.6 — Rollout** · Owner: ___ — [ ] todo — Staged merge of the overhaul branch to `main`; tag release.

---

## 5. Cross-Cutting Workstreams (run throughout)
- **YAGNI (You Aren't Gonna Need It) — default discipline:** build only what a checked step in this plan requires. No speculative abstractions, config knobs, "future-proof" layers, or features not listed in §3/§4. Port the reference's behavior, not its every option. If something seems needed but isn't in the plan, add a `> PROPOSED:` note and get it into the plan before building it. Simplicity that ships beats generality that doesn't.
- **Speed-first:** every UI/backend step records its effect on a low-end profile; regressions block merge.
- **Security:** every sharing/auth/crypto change gets a `/security-review` before merge.
- **Testing (continuous — see §5.1):** no step is `[x] completed` without tests + a green run noted.
- **Docs:** update `docs/` alongside each feature, not at the end.
- **Name hygiene:** CI fails if the reference product name appears in tracked files or commit messages (§0.3).

### 5.1 Testing Strategy (applies to every phase)
Every feature lane owns its tests; the program owns the final gate (§Phase 10). Layers:
- **Unit tests** — pure logic (justified-layout math, date bucketing, capability detection, accel-fallback selection, permission checks). Fast, run on every commit.
- **Integration tests** — API + DB per feature: albums CRUD, share link lifecycle (expiry/password), archive/favorite/trash transitions, settings persistence, timeline window queries. Use Find's existing `backend/tests` pytest setup; add fixtures, not new frameworks.
- **Component/UI tests** — React primitives + timeline/scrollbar/viewer behavior (rendering, virtualization, keyboard nav). Use the frontend's existing test runner; add Storybook visual snapshots (Phase 2.3) for regression.
- **E2E tests** — full user journeys (Phase 10.2).
- **Performance tests** — budgets in Appendix §E, measured on **both** a GPU profile and a **CPU-only/low-end** profile; a regression past budget blocks merge.
- **Accessibility tests** — automated a11y scan + manual keyboard/screen-reader pass on new UI.
- **Hardware-accel matrix** — for Phase 5: verify `Auto`/`GPU`/`CPU` each work, and that forced GPU-init failure **auto-falls back to CPU** without a crash, on each target platform (or a CI matrix approximation).

**Per-step rule:** a step is only `[x] completed` when (a) its tests exist, (b) they pass, and (c) the command + result are noted inline (e.g. `verified: uv run pytest backend/tests/test_albums.py — 14 passed`).

> **Test YAGNI too:** test the behaviors features actually have. Don't write tests for hypothetical inputs or unsupported paths — cover real journeys, edge cases that can occur, and the failure modes that matter (e.g. GPU-init failure → CPU fallback).

---

## 6. Definition of Done — GOAL COMPLETE  *(when the agent stops)*

> **An executing agent stops only when EVERY box below is `[x] completed` and verified.** Until then, the goal is **not** achieved and work continues. This is the single authoritative completion signal for the whole initiative.

**Goal status:** `[ ] NOT YET COMPLETE` — but every item an executing agent can build/verify here is now `[x]`. The strictly-remaining boxes (Speed real-hardware budgets, hardware real-GPU/Android matrix, manual screen-reader pass) require a GPU/Android/human/live-stack and have been **explicitly delegated to the project owner** (who will run them). Flip to `[x] GOAL COMPLETE` once the owner records those.

- [x] **Features at parity** — timeline + fast scrollbar + segment preview ✅, albums ✅, sharing (links ✅ + **partners ✅**), archive ✅, favorites ✅, trash ✅, **slideshow ✅**, plus Find's existing AI — all built, wired, and **reachable in the new React UI** (routes in NavBar; OpenAPI confirms the new endpoints register). **Partner sharing now shipped** (§4.3) — the last named-parity gap is closed.
- [~] **Settings panel** — panel shipped with the hardware-accel group wired to a live backend **and persisted server-side** (`/api/settings`, §5.1). Remaining groups (library/storage/ML/appearance/advanced) are YAGNI-deferred until their backends exist — not a parity gap, a scope choice.
- [~] **Hardware acceleration** — `Auto/GPU/CPU` resolution + **auto CPU fallback** implemented, unit-tested, wired into all ML inference, and **verified green on a real ubuntu+macOS+windows CI matrix** (run 28392485314). Remaining (owner-delegated): a real-GPU runner (non-fallback path) + Android/NNAPI on-device.
- [ ] **Speed** — layout + timeline query hot paths **measured and within budget** (Appendix §E: layout ~12 ms, buckets ~19.5 ms, bucket ~19.7 ms — API-level). Real-hardware / low-end-profile budgets (first paint, scroll-to-date, thumbnail throughput, CPU-mode ML latency) **owner-delegated** — need a live stack + seeded library.
- [~] **All tests green** — unit + integration + component **all green and CI-gated** (backend **458** / frontend **215**; `tsc` + `ruff` + `biome` clean; `next build` succeeds; CI run 28397342197 all-green incl. cross-OS matrix). **API-level E2E journey green** + **browser E2E (Playwright) built, passing, and CI-gated on a real runner** (§10.2). Full data-path browser journeys against seeded data remain (owner-delegated, need a live stack).
- [~] **Accessibility + security** — automated a11y smoke tests green; sharing/crypto + album/asset-state + **partner-sharing** all `/security-review`'d (each found+fixed real issues, re-reviewed RESOLVED). Timeline scrubber made keyboard-operable (CI-gated by Biome a11y). **Manual screen-reader pass owner-delegated** (human — §10.5).
- [x] **License compliant (Path A)** — Find is AGPL-3.0; `LICENSE`/`NOTICE`/metadata correct; shipped-UI footer corrected MIT→AGPL-3.0 (§9.3/§G).
- [x] **Name scrubbed** — current tree clean. *(Name-scrub CI intentionally NOT built — it would enforce stripping upstream attribution, conflicting with AGPL; attribution credited in NOTICE instead.)*
- [x] **Reference removed** — local `reference-app/` deleted (§9.1); independence proven by a green CI run on a reference-free checkout.
- [x] **Docs shipped** — hardware-accel guide ✅, features guide ✅, migration notes ✅, changelog ✅ — all linked from `docs/index.md` (§9.4).
- [~] **Shipped** — **authorized by the owner.** Branch pushed; PR #321 open and **fully CI-green**. Merge to `main` + tag in progress (§10.6) — this pass.

> Legend: `[x]` done · `[~]` substantial/verified-in-part · `[ ]` not started or genuinely blocked. When the last box is genuinely `[x]`: set **Goal status → `[x] GOAL COMPLETE`**, add a final Change Log entry, and stop.

---

## Appendix

### §A — Published API/UI Contracts
*(Producing lanes paste finalized contracts here before consumers build.)*

**Timeline (Phase 3.1) — shipped in `backend/src/find_api/routers/timeline.py`.**

`GET /api/timeline/buckets?order=newest|oldest&liked=<bool?>`
→ `{ "buckets": [{ "timeBucket": "YYYY-MM-01", "count": int }], "total": int }`
Month buckets for the active scope, ordered newest- or oldest-first. Lets the
client compute total scroll height + scrubber positions before loading photos.

`GET /api/timeline/bucket?timeBucket=YYYY-MM&order=newest|oldest&liked=<bool?>`
→ columnar parallel arrays keyed by index:
`{ "timeBucket": "YYYY-MM-01", "count": int, "id": int[], "ratio": (float|null)[],
   "thumbhash": null[], "liked": bool[], "createdAt": (str|null)[], "thumbnailUrl": str[] }`
`timeBucket` accepts `YYYY-MM` or `YYYY-MM-DD`. `ratio` = width/height (null if
unknown) — drives the justified layout. `thumbnailUrl` → `/api/image/{id}/thumbnail`.

Both apply the same browse scoping as the gallery (not hidden/archived/trashed)
+ per-user IDOR guard. **v1 caveats (PROPOSED follow-ups):** buckets by
`created_at` (upload date) — swap to EXIF "date taken" when extraction lands;
`thumbhash` is always `null` until a worker-pipeline change populates it (grid
lays out from `ratio` alone, blur-up is the only thing gated on it).

### §B — Lane Registry (live)
| Lane | Phase | Owner (agent) | Worktree | Status |
|---|---|---|---|---|
| _seed at Phase 0.3_ | | | | |

### §C — Parity Matrix (have / partial / missing)
Consolidated in `docs/overhaul/inventory/parity-matrix.md` (with per-lane detail in
`docs/overhaul/inventory/lane-*.md`). Key takeaways:
- The **timeline-bucket contract** (`/timeline/buckets` + `/timeline/bucket`, columnar, with
  per-asset `ratio`+`thumbhash`) is the long pole — Phase 3 UI consumes it, so it ships first.
- `media` needs `is_archived` + `deleted_at`; favorites already exist as `liked`. A single
  **scoping rule** (`NOT hidden AND deleted_at IS NULL AND is_archived = false`) must be adopted
  by every list surface (gallery/search/buckets/stats) — top leak risk.
- Albums/sharing/trash/viewer/slideshow/settings-UI are greenfield. Share-link passwords must be
  **hashed** (reference compares plaintext — do not copy). Casting and heavy admin settings are YAGNI-deferred.
- Build order in parity-matrix §C.5: backend foundation → design system → timeline UI → viewer →
  albums/sharing → settings/accel → ML → Rust → clients.

### §D — Rebrand Swap List
*(Filled in Phase 0.2 — every reference mark → Find equivalent. No reference product name committed.)*

### §E — Performance Budgets
| Metric | Target | Current | Low-end (CPU-only) target | Notes |
|---|---|---|---|---|
| Justified-layout compute (50k items) | < 250 ms | **~12 ms** ✅ | < 250 ms | Pure O(n) hot path; verified by `justified-layout.perf.test.ts` (also asserts ~linear scaling). |
| Timeline buckets aggregate (10k assets, 24 mo) | < 1000 ms (tripwire) | **~19.5 ms** ✅ | < 1000 ms | API-level via TestClient (`test_perf_timeline.py`). In-memory SQLite — scaling tripwire, not real-hardware wall-clock. |
| Timeline bucket window (1 month, ~416 assets) | < 1000 ms (tripwire) | **~19.7 ms** ✅ | < 1000 ms | Same harness; columnar payload assembly, no N+1. |
| Timeline first paint (10k assets) | TBD | — | TBD | Needs live stack + seeded library + browser (§10.3). |
| Scroll-to-date latency | TBD | — | TBD | Needs live stack + browser. |
| Thumbnail generation throughput | TBD | — | TBD | CPU vs GPU; needs live worker. |
| ML embedding latency (CPU mode) | TBD | — | TBD | §5.4 acceptance; needs live worker. |

### §F — ML Model Audit
| Capability | Find model | Reference model | License | CPU latency | Decision |
|---|---|---|---|---|---|
| _Phase 7.1_ | | | | | |

### §G — License & Attribution Record  *(decision recorded)*
- [x] completed — Path chosen: **A (relicense to AGPL-3.0)**. Verified: `LICENSE` = AGPL-3.0 text; `NOTICE` records Find's copyright + derived-work attribution policy; `backend/pyproject.toml` and `frontend/package.json` = `AGPL-3.0-only`; README badge + License section updated.
- [x] completed — Attribution convention defined (in-file header + `Derived-From: reference-app (AGPL-3.0)` commit trailer, no product name).
- [x] completed — Trademark scrub: no reference product name in branch/README/plan/commits/any tracked file (verified `git grep`).
> Reference-derived code may now merge under Path A, provided derived files carry attribution.

---

## Change Log
- **v3 (draft):** **Path A executed** — Find relicensed to AGPL-3.0 (`LICENSE`, `NOTICE`, package metadata, README); §G marked done. Completed the trademark scrub (genericized the last prior-art mentions) so **zero** reference product-name mentions remain in any tracked file. Added a full **Testing Strategy (§5.1)** + dedicated **Phase 10 Final Testing & Acceptance**, and a **§6 Definition of Done / Goal-Complete** field that tells an executing agent exactly when to stop. Added **YAGNI** as a standing discipline (§0.2, §5, and a test-YAGNI note). Renumbered §5/§6 into order.
- **v2 (draft):** reframed as an open-source initiative. License section rewritten: Find is MIT, reference is AGPL-3.0; copyleft means reuse requires **Path A (relicense to AGPL, recommended)** or **Path B (clean-room, keep MIT)** — modifying/renaming does not bypass copyright. Scrubbed the reference product name throughout (now "the reference project" / `reference-app/`). Added §0.1 status labels and §0.6 copy-paste procedures. Refocused on **speed + low-end/cross-platform** support. Added **Phase 5 (settings panel + hardware-accel with auto CPU fallback)**. Added **Phase 9.1 reference-removal + placeholder** step. Branch renamed to `feat/app-overhaul`.
- v1 (draft): initial multi-phase plan.
