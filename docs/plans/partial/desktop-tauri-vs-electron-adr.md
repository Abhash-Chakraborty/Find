# ADR: Desktop Framework Evaluation (Tauri vs Electron)

- **Status:** Partially complete
- **Date:** 2026-05-16
- **Last reviewed:** 2026-05-28
- **Owner:** Find maintainers
- **Related:** Discussion #37, Issue #49

**Current implementation status:** The Tauri prototype exists and validates the first shell direction. The production framework decision is not fully closed because backend sidecar packaging, process lifecycle, updater/signing, and cross-platform release validation are still unresolved.

## Context

Find is a local-first image intelligence platform currently delivered as a web application (Next.js frontend + FastAPI backend + worker pipeline).

If Find adds desktop packaging, the chosen framework must support secure local orchestration of the full local stack, not only a web shell.

That stack includes:

- Next.js frontend build output (`.next/` by default from `next build`)
- FastAPI API process
- Worker process and queue path (RQ + Redis)
- PostgreSQL + pgvector for metadata and embeddings
- Object storage (MinIO/S3-compatible) for media files
- Optional local ML/runtime dependencies depending on mode

## Decision statement (proposal)

Tauri is the **primary framework candidate** for initial desktop investigation due to lower runtime overhead and stronger default hardening posture.

Electron is the **evaluated fallback candidate** if Tauri-specific blockers appear during implementation spikes.

This ADR does **not** authorize building two desktop implementations in parallel.

## Goals

- Keep framework choice evidence-based and reversible
- Avoid parallel implementation tracks
- Minimize installer size and idle resource usage where feasible
- Preserve secure local-process boundaries for backend/worker sidecars
- Support Windows/macOS/Linux packaging and update workflows

## Non-goals

- Shipping both Tauri and Electron apps simultaneously
- Finalizing a production installer pipeline in this ADR alone
- Replacing existing web architecture

## Option A: Tauri

### Strengths

- Smaller baseline bundle size than Electron in typical apps
- Faster cold startup and lower idle memory in many workloads
- Rust-based host process with stricter-by-default API exposure model
- Good fit when the UI is already web-based and rendered in a native webview

### Constraints / risks

- Sidecar orchestration and cross-platform process packaging need careful setup
- Auto-update flow requires release/channel planning and signing discipline
- Team familiarity may be lower compared with Node-first Electron workflows

### Notes on updater capabilities

Tauri updater is **not limited** to Tauri Cloud. It can also work with static JSON metadata served from locations such as GitHub Releases or S3-compatible storage, provided signing/versioning are configured correctly.

## Option B: Electron

### Strengths

- Mature ecosystem and tooling for packaging/distribution
- Broad community references for updater and release workflows
- Node runtime in main process can simplify some process-control patterns

### Constraints / risks

- Larger baseline app size and higher memory footprint are common
- Broader attack surface requires strict hardening and secure defaults
- Potentially slower startup compared with Tauri for comparable shells

## Security considerations (both options)

Both frameworks embed a web renderer model (Electron Chromium renderer; Tauri system webview). Security posture depends on implementation discipline, not framework branding alone.

Minimum controls required regardless of framework:

- Strict local origin allowlists and protocol validation
- No untrusted remote content loading by default
- Explicit IPC allowlist and argument validation
- Signed artifacts and verified update metadata
- Secure handling of local credentials/tokens/config paths
- Principle of least privilege for spawned sidecar processes

## Sidecar/backend packaging reality check

For Find desktop mode, framework choice does not remove backend packaging complexity.

Both Tauri and Electron still require a strategy for bundling and launching:

- Python executable/runtime for FastAPI and worker sidecars
- Redis service path (embedded, bundled, or user-provided)
- PostgreSQL/pgvector strategy (embedded vs managed local dependency)
- Object storage strategy for media (embedded MinIO vs external/local service)

Frameworks differ mostly in orchestration ergonomics and host/runtime overhead, not in eliminating these dependencies.

## Comparison summary

| Area | Tauri | Electron |
| --- | --- | --- |
| Installer/app footprint | Typically smaller | Typically larger |
| Startup and idle memory | Typically lower | Typically higher |
| Process control ergonomics | Strong but may need more custom setup | Mature Node-based patterns |
| Updater ecosystem | Mature enough; supports static JSON + hosted artifacts | Very mature ecosystem |
| Security baseline | Strong defaults with explicit API exposure | Strong when hardened correctly; requires strict config |
| Fit with current Next.js app | Good (web frontend in webview) | Good (web frontend in Chromium) |

## Proposed evaluation plan

1. Run a time-boxed Tauri spike focused on:
   - launching frontend + API + worker
   - packaging approach for Python runtime
   - dev/prod process lifecycle reliability
2. Validate installer behavior on Windows/macOS/Linux (at least smoke level)
3. Test update path using signed metadata/artifacts
4. Measure practical metrics (installer size, cold start, idle memory)
5. Decide go/no-go using fallback triggers below

## Fallback triggers (choose Electron over Tauri when…)

Electron should be selected only if one or more of these are demonstrated and unresolved after a bounded spike:

- Tauri sidecar lifecycle is unreliable across target OSes under realistic Find workloads
- Update/signing workflow cannot meet release reliability requirements in acceptable effort
- Python runtime packaging with Tauri is repeatedly brittle beyond acceptable maintenance cost
- Required desktop integration APIs are blocked or unstable in Tauri for project needs
- Team delivery risk becomes high due to unresolved Tauri-specific issues and timeline pressure

Preference or familiarity alone is **not** a valid trigger.

## Scope guardrail

- Keep one active implementation path at a time.
- If fallback is triggered, formally record the switch in a follow-up ADR update.
- Do not maintain parallel desktop codebases.

## Open questions

- What is the final local dependency packaging model (embedded vs prerequisite services)?
- Which update channel strategy is acceptable for OSS contributors and maintainers?
- What signing/notarization workflow is sustainable for cross-platform releases?
- Which baseline hardware/profile should be used for footprint and startup benchmarks?

## Consequences

If Tauri succeeds, Find gets a lean desktop host with a single implementation path.

If fallback triggers are met, Electron is adopted with explicit rationale and without parallel-track drift.

Either way, the decision remains traceable, evidence-based, and aligned with local-first architecture constraints.
