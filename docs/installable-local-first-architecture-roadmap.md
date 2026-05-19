# Installable Local-First Architecture Roadmap for Find

**Status:** Proposed  
**Date:** 2026-05-15  
**Related:** [Issue #41](https://github.com/Abhash-Chakraborty/Find/issues/41), [Discussion #36](https://github.com/Abhash-Chakraborty/Find/discussions/36), [Discussion #37](https://github.com/Abhash-Chakraborty/Find/discussions/37), [Discussion #38](https://github.com/Abhash-Chakraborty/Find/discussions/38), [Discussion #39](https://github.com/Abhash-Chakraborty/Find/discussions/39)

## Why this roadmap exists

Find is already a strong local-first web app, but the current Docker-based runtime is aimed at contributors rather than normal users. Issue #41 asks for a clearer installable architecture so Find can ship as a desktop app first, keep its privacy promise, and leave room for mobile later.

The important constraint is simple: **packaging must not turn Find into a hosted cloud product by accident**. Users should be able to install Find and keep their images, embeddings, and search index on their own machine by default.

## Recommended direction

### Desktop MVP

Use **Tauri** as the default desktop shell.

Why:

- Small installer footprint compared with Electron.
- Better fit for a privacy-sensitive local-first product.
- Good match for a Rust supervisor that launches and monitors local sidecar services.
- The current Next.js frontend can still be reused as the UI layer.
- Rust is a better place than the renderer for path resolution, health checks, updates, and lifecycle control.

Keep **Electron** as the fallback if update handling, packaging, or sidecar lifecycle management becomes a real blocker.

### Mobile strategy

Ship **PWA first** for mobile.

Why:

- It reuses the existing frontend.
- It lets mobile connect to a user-owned desktop or server instance.
- It avoids pretending full on-device ML is a realistic first milestone.

Add Capacitor only if the PWA proves valuable and needs native device access later.

## Runtime matrix

| Mode | Purpose | Local-first? | Notes |
|---|---|---:|---|
| Current Docker web stack | Contributor/dev environment | Yes | Best for development and GPU-backed local ML, not for ordinary end users. |
| Desktop MVP local stack | Installable app for Windows/macOS/Linux | Yes | Default user-facing target. No Docker required. |
| Mobile PWA companion | Browse/upload from a phone | Yes, if it connects to a user-owned backend | Works against the user’s own laptop, NAS, or home server. |
| Optional self-hosted accelerator | Advanced local/server mode | Yes | User-owned endpoint for heavier processing or sync. |
| Optional remote/cloud mode | Explicit opt-in only | Sometimes | Must be clearly labeled and never the default. |

## Proposed desktop architecture

```text
Tauri shell
  ├─ Next.js UI bundle
  ├─ Rust app layer
  │   ├─ process supervisor
  │   ├─ update / version manager
  │   ├─ app-state + config loader
  │   ├─ file-path + storage resolver
  │   └─ frontend ↔ backend IPC bridge
  ├─ Packaged local services
  │   ├─ FastAPI API sidecar
  │   ├─ background worker sidecar
  │   ├─ metadata/job store
  │   ├─ local blob store
  │   └─ model cache
  └─ Optional self-hosted accelerator endpoint
```

### Rust responsibilities

Rust should own the parts where deterministic process control matters:

- Resolve app data, cache, logs, and binary paths per platform.
- Start sidecars in a controlled order and wait for readiness probes.
- Restart or terminate children cleanly on app exit.
- Surface health, progress, and failures back to the UI.
- Guard the boundary between the renderer and the local runtime.

Rust should **not** absorb the ML stack itself. The shell should orchestrate, not become a second backend.

### What runs locally by default

- UI shell and all application screens.
- API process.
- Background processing worker.
- Metadata database.
- Image/object storage.
- Job queue or queue-equivalent persistence.
- Model cache on the user’s device.
- Search, upload, indexing, clustering, and gallery browsing.

### Practical storage shape

For an installable desktop build, the most realistic layout is:

- **SQLite** for app metadata, job state, and sync/pairing records.
- **Filesystem storage** for original images and derived artifacts.
- **Per-user cache directories** for downloaded models and temporary processing files.

That is a much better fit for a desktop installer than forcing end users to manage PostgreSQL, Redis, and MinIO on their own machine. Those remain the developer and server story.

### What stays optional

- Large model packs that can be downloaded on demand.
- Advanced GPU acceleration.
- Self-hosted server acceleration.
- Sync across user-owned devices.
- Any remote processing path.

## Data-layer recommendation

The desktop installer should minimize external prerequisites. The current stack uses PostgreSQL, Redis, and MinIO, but those are not ideal as mandatory user-facing installs.

Recommended packaging stance:

1. **Metadata and app state** should move to a local embedded database, most likely SQLite.
2. **Image blobs** should live in a local app-managed file store.
3. **Queue state** should be local and private to the app install.
4. **Models** should be cached per user and downloaded only when needed.
5. **PostgreSQL, Redis, and MinIO** should remain optional for advanced self-hosted deployments, not hard requirements for the desktop installer.

That gives Find a real installable story without forcing users to learn Docker just to open their own photo library.

## Packaging target

### Desktop MVP target

The first shippable installer should aim for:

- A single installer per platform.
- No Docker requirement.
- Local-first defaults enabled out of the box.
- Model downloads deferred until first use.
- Clear progress UI for model and index setup.
- Packaged sidecars with versioned binaries, not loose developer source trees.
- A Rust-controlled startup sequence: shell first, local services second, UI last.

For the sidecars, the release build should produce self-contained executables per platform. That can be done with Python packaging tools, but the important part is that the Tauri app only has to supervise binaries and verify health, not bootstrap a developer environment.

### Size guidance

These are target ranges, not hard guarantees:

- **Tauri shell only:** roughly tens of MB.
- **Desktop MVP with bundled local runtime:** aim to stay well under a few hundred MB compressed before optional model packs.
- **First-run disk use:** keep the base install modest, then let optional model packs add the larger footprint on demand.

The important product rule is not the exact number; it is that users can install Find without pulling in the full Docker contributor stack.

## Local-first non-negotiables

1. **Default mode stays local.**
2. **No silent upload** of images, embeddings, or metadata to a hosted service.
3. **Remote processing is opt-in and explicit.**
4. **Users own the backend** if they use one outside their desktop install.
5. **The UI must say where the data lives** and which backend is active.
6. **Privacy boundaries must be visible** before any networked processing starts.

## Security and trust boundaries

- Use encrypted transport for any non-local connection.
- Keep API access limited to the Find app and user-approved endpoints.
- Never expose Redis, PostgreSQL, or object-store internals directly to the client.
- Show the active backend and whether it is local, LAN-hosted, or self-hosted elsewhere.
- Make remote mode reversible, with a clear escape hatch back to fully local behavior.

## Phased roadmap

### Phase 1: Desktop shell proof

- Launch the Next.js UI inside Tauri.
- Start and stop a packaged local FastAPI sidecar cleanly.
- Wire health checks and graceful shutdown.
- Prove the app can open with no Docker runtime.
- Validate that the Rust layer can resolve paths, spawn children, and recover from a failed backend startup.

### Phase 2: Local runtime packaging

- Bundle the worker and local persistence layer.
- Replace mandatory external services with app-managed local storage.
- Add model cache management and download progress UI.
- Introduce a SQLite-backed local data path if the Python stack still assumes PostgreSQL for desktop.

### Phase 3: Mobile companion MVP

- Ship a PWA with installability and responsive layouts.
- Add pairing to a user-owned desktop/server instance.
- Keep offline shell caching and queued uploads.

### Phase 4: Optional advanced modes

- Add self-hosted acceleration.
- Add GPU-accelerated or larger model packs.
- Add Capacitor only if the PWA proves the need for native device APIs.

## Follow-up implementation work

The roadmap should be broken into implementation issues after this architecture is accepted:

- Desktop shell bootstrap and sidecar lifecycle management.
- Local data-store replacement plan.
- Model cache and first-run download UX.
- Mobile PWA installability and pairing flow.
- Remote-acceleration trust model and settings UI.

## Bottom line

**Desktop first, local by default, mobile as a companion.**

Tauri is the best default desktop shell, Electron is the fallback if packaging friction gets in the way, and mobile should start as a PWA rather than a full native ML app. The Rust layer should supervise processes and system state; Python should keep the API and ML work. That combination preserves Find’s local-first identity while making it realistic to install.