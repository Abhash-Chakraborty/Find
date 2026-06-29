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

> **Default assumption for this plan: Path A.** Phases below are written for Path A (free reuse + attribution). If Path B is chosen, every "port" step gains a spec-extraction sub-step and verbatim copies of code (not assets) are disallowed.

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

- **Stage 1.1 — Feature inventory** *(lanes run concurrently)*
  - Lane A (Timeline/grid) · Owner: ___ — [ ] todo — Map reference `web/` timeline, scrollbar, segment preview, justified layout → behaviors + data needs.
  - Lane B (Albums/sharing) · Owner: ___ — [ ] todo — Map album CRUD, shared links, partner sharing, permissions.
  - Lane C (Archive/favorites/trash) · Owner: ___ — [ ] todo — Map archive/favorite/trash/restore flows.
  - Lane D (Slideshow/viewer) · Owner: ___ — [ ] todo — Map asset viewer (zoom/pan/keyboard), slideshow, casting.
  - Lane E (Backend/API) · Owner: ___ — [ ] todo — Map reference server endpoints + DB schema for the above; diff against Find's FastAPI.
  - Lane F (ML) · Owner: ___ — [ ] todo — Compare reference ML (CLIP/face/ONNX) vs Find models; list adopt/keep candidates + model licenses.
  - Lane G (Settings/config) · Owner: ___ — [ ] todo — Map the reference **settings panel** structure (every config group/field) → Find settings spec; note where hardware-accel belongs.
  - Lane H (Mobile/desktop) · Owner: ___ — [ ] todo — Inventory reference Flutter feature surface; note what maps to a future Find client.
- **Stage 1.2 — Gap analysis & sequencing**
  - [ ] todo — Consolidate lanes into a parity matrix (have / partial / missing) in Appendix §C.
  - [ ] todo — Order features by value vs effort; confirm Phase 3–8 scope.

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
  - [ ] todo — Define time-bucket API (counts per period) + asset-window endpoints (FastAPI). Publish types in Appendix §A.
- **Stage 3.2 — Justified grid** · Lane · Owner: ___
  - [ ] todo — Port justified-layout algorithm to React; **virtualized rendering** so large libraries stay smooth on weak hardware.
- **Stage 3.3 — Fast scrollbar + segment preview** · Lane · Owner: ___
  - [ ] todo — Date-scrubber scrollbar with segment hover previews, driven by the 3.1 contract.
- **Stage 3.4 — Asset viewer + slideshow** · Lane · Owner: ___
  - [ ] todo — Full-screen viewer (zoom/pan, keyboard nav), thumbnail-vs-full-res discipline, slideshow mode.
- **Stage 3.5 — Navigation & shells** · Lane · Owner: ___
  - [ ] todo — App shell, sidebar, responsive layouts; **mobile-web/touch friendly**.
- **Stage 3.6 — Integration & perf**
  - [ ] todo — Wire timeline to live Find gallery API; verify on a large seeded library; record perf budget (Appendix §E), including a **low-end profile** (no GPU, limited RAM).

### PHASE 4 — Backend Feature Parity (FastAPI)
**Goal:** Find APIs/DB support the new features. *(~4–6 weeks; lanes parallel)*

- **Stage 4.1 — Schema & migrations** · Owner: ___
  - [ ] todo — Add tables/columns for albums, shares, archive flag, favorites, trash. Alembic migrations + rollback.
- **Stage 4.2 — Albums** · Lane · Owner: ___ — [ ] todo — CRUD, asset membership, cover, ordering, tests.
- **Stage 4.3 — Sharing** · Lane · Owner: ___ — [ ] todo — Shared links (expiry, password, permissions) + partner sharing; **security review required**.
- **Stage 4.4 — Archive / favorites / trash** · Lane · Owner: ___ — [ ] todo — State + filtered queries integrated with gallery scoping; tests.
- **Stage 4.5 — Activity/log surface** · Lane · Owner: ___ — [ ] todo — The functional archive/log surface Find lacks; define + implement.
- **Stage 4.6 — API contract publish**
  - [ ] todo — Regenerate OpenAPI + TS client; hand to Phase 3 consumers.

### PHASE 5 — Settings Panel & Hardware Acceleration  *(core of the speed/low-end goal)*
**Goal:** one settings panel for all config, plus a hardware-accel layer that uses the GPU when available and **falls back to CPU automatically** on any platform. *(~2–4 weeks)*

- **Stage 5.1 — Settings panel UI** · Lane · Owner: ___
  - [ ] todo — Build a Find settings panel (React), structured from the Phase 1 Lane G spec: general, library/storage, ML, sharing, appearance, advanced.
  - [ ] todo — Persist settings via a Find settings API; validate + migrate existing config.
- **Stage 5.2 — Hardware capability detection** · Lane · Owner: ___
  - [ ] todo — Detect available accelerators per platform: CUDA/ROCm (Linux/Win), CoreML/Metal (Apple), DirectML (Win), NNAPI (Android), and **CPU baseline** everywhere. Expose a capability report to the settings panel.
- **Stage 5.3 — Accel toggle + auto-fallback** · Lane · Owner: ___
  - [ ] todo — Settings toggle: `Auto` (use best available), `GPU`, `CPU`. On unsupported/failed GPU init, **automatically fall back to CPU** and surface a non-blocking notice. No crash, no hard dependency on a GPU.
  - [ ] todo — Wire ONNX Runtime execution providers accordingly; choose CPU-friendly model variants when in CPU mode.
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

### PHASE 9 — Reference Removal, Integration, QA & Rollout
**Goal:** remove the reference copy, prove independence, ship. *(~2–3 weeks)*

- **Stage 9.1 — Reference removal** · Owner: ___
  - [ ] todo — Confirm no reference source is committed (`git ls-files | grep -i` checks); confirm derived files carry attribution (Path A).
  - [ ] todo — **Delete `reference-app/` locally and replace with placeholder images** in any fixture/sample dirs that referenced it; confirm the app builds/runs without the reference present.
- **Stage 9.2 — E2E** · Owner: ___ — [ ] todo — Cross-feature E2E (upload→timeline→album→share→archive→slideshow→settings/accel toggle).
- **Stage 9.3 — Perf & a11y** · Owner: ___ — [ ] todo — Large-library perf budgets incl. **CPU-only/low-end**; accessibility pass on new UI.
- **Stage 9.4 — Compliance close-out** · Owner: ___ — [ ] todo — Verify §1 license/attribution obligations satisfied; verify name-scrub CI is green.
- **Stage 9.5 — Docs & rollout** · Owner: ___ — [ ] todo — User/dev docs (incl. hardware-accel guide), migration notes, changelog; staged merge of the overhaul branch to `main`; tag release.

---

## 5. Cross-Cutting Workstreams (run throughout)
- **Speed-first:** every UI/backend step records its effect on a low-end profile; regressions block merge.
- **Security:** every sharing/auth/crypto change gets a `/security-review` before merge.
- **Testing:** no step is `[x] completed` without tests + a green run noted.
- **Docs:** update `docs/` alongside each feature, not at the end.
- **Name hygiene:** CI fails if the reference product name appears in tracked files or commit messages (§0.3).

---

## Appendix

### §A — Published API/UI Contracts
*(Producing lanes paste finalized contracts here before consumers build. Empty until Phase 3.1/4.6.)*

### §B — Lane Registry (live)
| Lane | Phase | Owner (agent) | Worktree | Status |
|---|---|---|---|---|
| _seed at Phase 0.3_ | | | | |

### §C — Parity Matrix (have / partial / missing)
*(Filled in Phase 1.2.)*

### §D — Rebrand Swap List
*(Filled in Phase 0.2 — every reference mark → Find equivalent. No reference product name committed.)*

### §E — Performance Budgets
| Metric | Target | Current | Low-end (CPU-only) target | Notes |
|---|---|---|---|---|
| Timeline first paint (10k assets) | TBD | — | TBD | |
| Scroll-to-date latency | TBD | — | TBD | |
| Thumbnail generation throughput | TBD | — | TBD | CPU vs GPU |
| ML embedding latency (CPU mode) | TBD | — | TBD | §5.4 acceptance |

### §F — ML Model Audit
| Capability | Find model | Reference model | License | CPU latency | Decision |
|---|---|---|---|---|---|
| _Phase 7.1_ | | | | | |

### §G — License & Attribution Record  *(one human decision — §1.2)*
- [ ] Path chosen: **A (relicense AGPL-3.0, recommended)** / B (clean-room MIT).
- [ ] If A: AGPL-3.0 applied; `LICENSES/`, `NOTICE`, attribution headers in place.
- [ ] Trademark scrub confirmed (no reference product name in branch/README/plan/commits/shipped artifacts).
> No reference-derived code merges until this is recorded.

---

## Change Log
- **v2 (draft):** reframed as an open-source initiative. License section rewritten: Find is MIT, reference is AGPL-3.0; copyleft means reuse requires **Path A (relicense to AGPL, recommended)** or **Path B (clean-room, keep MIT)** — modifying/renaming does not bypass copyright. Scrubbed the reference product name throughout (now "the reference project" / `reference-app/`). Added §0.1 status labels and §0.6 copy-paste procedures. Refocused on **speed + low-end/cross-platform** support. Added **Phase 5 (settings panel + hardware-accel with auto CPU fallback)**. Added **Phase 9.1 reference-removal + placeholder** step. Branch renamed to `feat/app-overhaul`.
- v1 (draft): initial multi-phase plan.
