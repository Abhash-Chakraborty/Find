# Mobile Strategy ADR: PWA First

**Status:** Proposed

**Date:** 2026-05-14

**Discussion:** #37

## 1. Goal

Define the first realistic mobile direction for Find without pretending the current Docker-based stack can be packed into a phone app.

Find is local-first, but the current product depends on PostgreSQL, Redis, MinIO, FastAPI, background workers, and ML dependencies that are not practical to bundle into a mobile runtime. Mobile therefore needs a staged approach that preserves local-first behavior while keeping the first milestone achievable.

## 2. Options compared

### 2.1 PWA only

**What it is:** A mobile web experience with installability, responsive layouts, service worker caching, and optional offline shell behavior.

**Strengths**

- Fastest path to something usable.
- Reuses the existing Next.js frontend.
- Works naturally with a running local or self-hosted Find backend.
- No native build system, app store packaging, or device-specific maintenance.
- Keeps the product aligned with local-first by connecting to a user-owned backend rather than a shared cloud service.

**Limitations**

- Limited native access to camera, background tasks, filesystem, push, and deep OS integration.
- Offline behavior is mostly shell-level caching, not full local processing.
- Depends on a reachable backend for indexing, search, and full gallery sync.

### 2.2 Capacitor companion app

**What it is:** A mobile shell around the web UI with access to native APIs such as camera, secure storage, share sheets, and device-specific permissions.

**Strengths**

- Better fit for image upload and mobile capture.
- Enables native niceties without rewriting the whole UI.
- Can still connect to a user-owned desktop/server instance.

**Limitations**

- More platform maintenance than a PWA.
- Still does not solve local ML on-device.
- Adds build and release complexity before the core mobile workflow is proven.

### 2.3 Fully native local mobile ML app

**What it is:** A dedicated mobile app that runs image intelligence locally on the device.

**Strengths**

- Strongest local-first story.
- Can keep everything on-device when the hardware allows it.

**Limitations**

- Highest complexity by far.
- Model size, memory pressure, battery cost, and mobile acceleration constraints make this a poor first milestone.
- Would require substantial model compression, runtime work, and mobile-specific ML engineering.

## 3. Recommendation

**Choose PWA only as the first MVP path.**

The PWA is a mobile companion to a user-owned Find desktop or server instance. It connects to the backend for search, index, and gallery operations — it does not run the Find stack (PostgreSQL, Redis, MinIO, ML models) on the phone. All heavy processing stays on the user's machine; the phone is a thin, capable client that relies on a reachable backend.

Reasoning:

1. It is the fastest realistic way to make Find mobile-friendly.
2. It preserves the local-first model by relying on a backend owned by the user.
3. It reuses the existing frontend with the least engineering overhead.
4. It keeps the team focused on proving the mobile user flow before investing in native wrappers or on-device ML.

This does **not** mean the long-term mobile plan is “web forever.” It means the first milestone should validate the mobile UX and API shape with the smallest possible surface area.

**MVP non-goals:** do not bundle the full Docker stack into a phone app, do not require on-device PostgreSQL/Redis/MinIO, and do not block the first mobile milestone on full local ML inference.

## 4. How mobile stays local-first

Mobile should not become a hosted SaaS frontend that happens to show images.

Instead, the mobile client should:

- Connect to a user-owned Find backend on the user’s laptop, NAS, home server, or self-hosted machine.
- Treat the backend as the source of truth for media, metadata, embeddings, and clusters.
- Cache only safe, user-specific presentation data on the device.
- Avoid moving ML processing into a shared cloud dependency.

This keeps the product local-first even when the phone itself is not doing the ML work.

## 5. Feature split

### 5.1 Works offline on-device

These are realistic for a PWA-style first milestone:

- App shell and navigation.
- Previously viewed thumbnails and cached metadata, subject to service worker cache limits.
- Recently opened item details that were already synchronized.
- Settings/help screens that do not require live backend calls.
- Draft states for forms, where the browser can retain them locally until reconnect.
- **Draft upload queue** — images selected offline are staged in IndexedDB with metadata; the PWA flushes them to the backend when connectivity is restored. Users can add, review, or remove queued items without a live connection.

### 5.2 Requires a user-owned endpoint

These need a running Find backend on a desktop or server instance:

- Uploading new images or ZIP archives.
- Full gallery browsing.
- Search across the full indexed library.
- View job status and indexing progress.
- Like/delete actions.
- Cluster browsing and cluster regeneration.
- Captions, OCR, object detection, embedding generation, and clustering.
- Any operation that reads the authoritative PostgreSQL, MinIO, or Redis-backed state.

### 5.3 Better suited for a later Capacitor layer

If the PWA proves valuable, a companion shell can add:

- Camera capture.
- Native share-sheet ingestion.
- Secure token storage.
- Push notifications for indexing completion.
- Biometrics or device unlock for app access.

## 6. Security requirements for connecting to a desktop/server instance

Mobile access must assume the backend may be reachable over a home network or tunnel, not just localhost.

Minimum requirements:

1. **Encrypted transport** — use HTTPS/TLS only; never send credentials or media over plain HTTP.
2. **Authentication** — JWT-based auth with short-lived access tokens (15 min) and longer-lived refresh tokens (7 days). The existing FastAPI backend needs a new `/api/auth/*` module handling login, token refresh, and logout.
3. **Pairing flow** — QR code encoding `{host, port, token}` scanned by the phone. The desktop/server generates this payload in-app. The pairing token is **single-use and short-lived** (expires in minutes); it is exchanged for session tokens during the first handshake and cannot be replayed. The phone stores the resulting connection profile. Manual fallback (host + port + pairing code) for devices without a camera.
4. **Short-lived tokens** — issue access tokens that expire and can be revoked. Refresh tokens are rotated on each use to limit damage from leaks.
5. **Origin and CORS restrictions** — only allow the specific mobile web origin(s) you expect.
6. **Least-privilege API exposure** — expose only the Find API, not Redis, PostgreSQL, MinIO, or worker internals.
7. **Rate limiting and request size limits** — protect upload and search endpoints from accidental abuse.
8. **Device-safe storage** — store refresh tokens in secure storage when a native shell is introduced. A PWA must not keep bearer or session secrets in `localStorage`; use HttpOnly, Secure, SameSite cookies or in-memory session handling instead. Client-side storage should keep only non-secret connection metadata such as host and port.
9. **User-visible trust model** — show which backend the phone is connected to, so users know whether they are using a laptop, home server, or remote instance.

## 7. What this means for the roadmap

The mobile roadmap should be staged as follows:

1. **Stage 1: PWA mobile web app**
   - Responsive UI — the existing frontend already has a gallery and search page; the first sub-task is adapting layouts with mobile-first CSS (stacked cards, bottom nav, touch-friendly hit targets). This reuses existing components and can ship independently of the pairing/auth work.
   - Installable app shell — use `@serwist/next` (actively maintained, Next.js 16 compatible) for service worker generation, precaching, and runtime caching. Configure a `manifest.json` with icons, theme color, and display mode.
   - Backend pairing / connection flow — QR code scanner or manual entry for host + port + pairing token. The pairing token is single-use and exchanged for short-lived session handling immediately; it is never stored. The PWA keeps only non-secret connection metadata such as host and port client-side, while any bearer or session secret uses HttpOnly cookies or in-memory handling. A later Capacitor shell can use secure storage where appropriate.
   - IndexedDB upload queue — offline image selection staged locally, flushed on reconnect.
   - Core browse, search, upload, and gallery actions — same API consumption as the desktop UI, adapted for mobile gestures and viewport.

2. **Stage 2: Companion shell if needed**
   - Add Capacitor only if native capabilities become necessary and the PWA hits clear limits.

3. **Stage 3: Native on-device ML only if justified**
   - Revisit only after the mobile UX, backend sync model, and real user demand are proven.

## 8. Decision

**MVP path:** PWA only.

**Why not Capacitor first?** It adds native surface area before the core mobile workflow is proven.

**Why not native ML first?** It is the most ambitious option and the least realistic for a first mobile milestone.

In short: prove the mobile experience with the web stack first, then earn the right to add native wrapper features later.

## 9. Related

- Discussion: issue #37
- Current architecture: [`../README.md`](../README.md)
