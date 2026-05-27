# Tauri Desktop Prototype

Proof-of-direction for wrapping the Find Next.js frontend in a Tauri desktop shell.
Implements **Phase 1** of the installable local-first architecture described in
[`installable-local-first-architecture-roadmap.md`](installable-local-first-architecture-roadmap.md).
Relates to issue #42 and discussion #37.

---

## Prerequisites

| Tool | Install |
|------|---------|
| Rust (stable) | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh`, then `rustup default stable` |
| Tauri system deps (macOS) | Xcode Command Line Tools — `xcode-select --install` |
| Tauri system deps (Linux) | `sudo apt install libwebkit2gtk-4.1-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev` |
| Node / pnpm | Install Node from https://nodejs.org, then run `npm install -g pnpm` |

---

## Build and run commands

### Development (hot reload via Next.js dev server)

```bash
cd frontend
pnpm install      # first time only
pnpm approve-builds   # if prompted about sharp, approve it, then re-run pnpm install
pnpm desktop:dev  # starts Next.js and opens the desktop window
```

Tauri's `beforeDevCommand` starts `pnpm dev`, and `devUrl` points the window at
`http://localhost:3000`. No static export is involved in development mode.

### Production build (static export → bundled app)

```bash
cd frontend
pnpm install
pnpm desktop:build
# Equivalent to:
#   pnpm build:static   -> writes frontend/out/
#   tauri build         -> reads frontend/out/, produces installer in src-tauri/target/release/bundle/
```

The installer is written to `frontend/src-tauri/target/release/bundle/`.

---

## Architecture

```text
frontend/
├── next.config.js          # NEXT_OUTPUT=static enables output:"export" + unoptimized images
├── package.json            # build:static / desktop:* scripts; @tauri-apps/cli devDep
└── src-tauri/
    ├── tauri.conf.json     # app metadata, window size, frontendDist, devUrl
    ├── capabilities/
    │   └── default.json    # Tauri v2 permission model (core:default)
    ├── Cargo.toml          # Rust crate (find-desktop)
    ├── build.rs
    └── src/
        ├── main.rs         # binary entry point
        └── lib.rs          # Tauri builder (extensible for future IPC commands)
```

The backend (FastAPI + workers) runs separately. `NEXT_PUBLIC_API_URL` must point
to it (default: `http://localhost:8000`). No backend bundling is in scope for this
prototype.

---

## What works with static export

- All pages (`/`, `/upload`, `/gallery`, `/search`, `/clusters`, `/people`) —
  they are pure client components with no server-side dependencies.
- Client-side data fetching via axios to the external FastAPI backend.
- Tailwind styles, React Query, Sonner toasts.
- Navigation and routing (static export with `trailingSlash: true` maps routes to
  `page/index.html` files that Tauri's WebView resolves correctly).

---

## Known blockers / issues

### 1. `next/image` optimization disabled

**Impact:** Medium  
Images served from MinIO (`localhost:9000`) are rendered as plain `<img>` tags.
No automatic resizing, lazy loading via Next.js, or format conversion (WebP).
Performance impact depends on average image size in the library.

**Fix path:** Use a CDN-compatible image host, or replace `next/image` with `<img>`
tags in gallery/search views and apply manual lazy loading.

---

### 2. Hardcoded `localhost` API and MinIO URLs

**Impact:** High for distribution  
`NEXT_PUBLIC_API_URL` and MinIO's `localhost:9000` are baked in at build time.
A distributed app cannot assume the backend is always on `localhost`.

**Fix path:** Make the API URL configurable at runtime via a Tauri IPC call that
reads a config file, or expose a settings screen before the first launch.

---

### 3. No backend lifecycle management

**Impact:** High for installable UX  
The desktop app assumes the Docker Compose stack (PostgreSQL, Redis, MinIO, FastAPI,
worker) is already running. A cold launch shows a blank/error state.

**Fix path:** Either (a) bundle the backend as Tauri sidecar processes (complex,
large installer), or (b) show a "backend not running" screen with instructions.
Option (b) is lower effort for a v1 install experience.

---

### 4. CSP is disabled (`"csp": null`)

**Impact:** Low for prototype, needs fixing before release  
Content Security Policy is turned off to allow `http://localhost:*` API calls.
For a signed release build this must be tightened.

---

## Electron fallback rationale

If Tauri is ruled out, Electron is the natural fallback:

| | Tauri | Electron |
|---|---|---|
| Installer size | ~5-15 MB | ~80-120 MB |
| Image optimisation | Blocked (static export) | Works (ships Node.js, can run Next.js server) |
| Backend sidecar | Possible but complex | Easier with child_process |
| Code signing | Supported | Supported |
| Maintenance burden | Rust required | JS only |

Electron's main advantage here is that it can run the Next.js standalone server
as a child process, eliminating the static export constraint entirely.
