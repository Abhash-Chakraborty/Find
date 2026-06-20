# Design: Optional Self-Hosted Remote Acceleration

**Status:** Not started  
**Issue:** [#47](https://github.com/Abhash-Chakraborty/Find/issues/47)  
**Author:** @Sanjaykumar-2005  
**Last reviewed:** 2026-05-28  
**Current implementation status:** No `ML_MODE=remote`, `REMOTE_ML_*` configuration, remote ML router, remote client, consent UI, or active remote-mode indicators are present in the current codebase.

---

## 1. Problem Statement

Find's local-first design means all ML inference — YOLOv10 object detection, Florence-2 captioning, PaddleOCR, and SigLIP ViT-B-16 embeddings — runs on the user's machine. The total model weight is approximately 1.5 GB and the `docker-compose.yml` requests an NVIDIA GPU with `count: 1`. This creates two concrete friction points:

- **GPU requirement:** Most consumer machines and all mobile devices cannot run the full ML stack at acceptable throughput.
- **Mobile access:** A mobile client has no practical path to local ML inference. Without a remote endpoint, a mobile client is read-only at best.

The goal is to allow users who already control a capable machine — a desktop, home server, or private VPS — to run ML there and have other devices (including mobile) submit work to it, while ensuring no image data ever leaves infrastructure the user controls, and making that guarantee explicit, visible, and user-controlled.

---

## 2. Non-Negotiables

These constraints must not be violated by any implementation that follows this design:

1. **Local mode is the default.** A fresh install with no configuration performs all ML locally. There is no remote endpoint pre-configured.
2. **No silent data transmission.** Images, OCR text, captions, embeddings, and metadata are never sent anywhere without an explicit, per-session user action.
3. **Remote mode is opt-in, not opt-out.** Enabling remote acceleration requires a deliberate toggle plus a consent step, not just filling in a URL field.
4. **Only user-controlled endpoints are supported.** There is no project-hosted cloud endpoint. The design must not accommodate one without a separate design review and privacy impact assessment.
5. **The UI must make remote mode visually unambiguous** while it is active — during processing and during search.

---

## 3. Prior Art: What Real Projects Actually Do

The following is based on reading actual documentation and source discussions, not assumptions.

### 3.1 Immich — Remote Machine Learning

Immich ([docs](https://docs.immich.app/guides/remote-machine-learning/), [architecture](https://docs.immich.app/developer/architecture/)) runs its ML pipeline as a separate Python/FastAPI container (`immich-machine-learning`) on port 3003. The main server communicates with it over HTTP, sending "the text or image payload" per request. Models are loaded in ONNX format for broad hardware compatibility and cached in memory after first load.

**To point at a remote ML server:** administrators go to Machine Learning Settings → Add URL (e.g., `http://ip:port`). Multiple URLs can be added; Immich tries them sequentially and temporarily skips unreachable ones. The old `IMMICH_MACHINE_LEARNING_URL` environment variable is deprecated in favour of the UI-based config.

**Critical finding:** The Immich documentation explicitly states that *"as an internal service, the machine learning container has no security measures whatsoever."* It relies entirely on network-level security (VPN, firewall, private LAN). Image previews are sent to the remote container. No bearer tokens, no TLS enforced by the service itself.

**Lesson for Find:** Immich's zero-auth approach works when the ML server is truly internal. For Find, where the user is explicitly choosing to send images to a remote endpoint (possibly over the internet), we must do better than zero auth. But the URL-based configuration and sequential fallback pattern are worth adopting.

### 3.2 Ollama — Pluggable Local Inference Endpoint

Ollama ([API docs](https://docs.ollama.com/api/introduction)) serves models at `http://localhost:11434/api` by default. Its API surface is intentionally small: `/api/generate`, `/api/chat`, `/api/embeddings`, `/api/tags`, `/api/ps`, and a health check at `/`. It also exposes an OpenAI-compatible layer at `/v1/`.

**Authentication:** There is no built-in authentication in Ollama. The project relies on localhost binding for local use and expects users to handle network-level security (reverse proxy with auth, VPN) for remote access.

**Lesson for Find:** The "small contract, user handles connectivity" pattern is correct. The API contract for Find's ML endpoints should be similarly minimal. However, since Find's ML endpoints handle images (far more sensitive than LLM prompts), authentication cannot be delegated entirely to the network layer.

### 3.3 PhotoPrism — Local-First with Optional Remote ML

PhotoPrism ([architecture](https://docs.photoprism.app/developer-guide/vision/service/setup/)) runs all ML in a single container by default. Its newer Vision service is designed as a decoupled microservice that can optionally run on a separate machine with a GPU. Like Immich, it uses no built-in auth on the ML microservice — it expects the service to be on a trusted network.

**Lesson for Find:** The "default local, optional remote" pattern has clear prior art in the photo management space. The precedent is consistent across tools.

### 3.4 Tailscale — Network Layer for Remote Access

Tailscale ([self-hosting guide](https://tailscale.com/blog/self-host-a-local-ai-stack)) creates a WireGuard mesh VPN. Devices on the same Tailnet reach each other regardless of physical network. `tailscale serve` proxies a local service and automatically provisions a valid TLS certificate with no manual configuration. MagicDNS assigns stable hostnames (e.g., `desktop.tail1234.ts.net`) so users don't manage IP addresses.

**Setup path:** Install Tailscale on both desktop and mobile → `tailscale serve 8000` on desktop → mobile accesses `https://desktop.tail1234.ts.net` with valid TLS. Free for up to 3 users and 100 devices.

**Lesson for Find:** Tailscale Serve removes the need for Find to implement its own TLS certificate management. For users comfortable installing Tailscale, this is the simplest secure path to mobile access.

### 3.5 Cloudflare Tunnel — Convenience with a Tradeoff

Cloudflare Tunnel ([docs](https://developers.cloudflare.com/tunnel/)) creates an outbound-only encrypted connection from the user's server to Cloudflare's network. No port forwarding or public IP is needed.

**The tradeoff:** Cloudflare terminates TLS at its edge before re-encrypting to the origin. This means Cloudflare can see the decrypted content of HTTP requests — including image bytes. The [security analysis](https://www.pieterdev.com/blog/cloudflare-tunnel/) from independent reviewers is consistent: this is acceptable for low-sensitivity services (media streaming, recipe apps) but "for sensitive applications like finance or medical records, alternatives like Tailscale should be considered."

**Lesson for Find:** Cloudflare Tunnel should be documented as an option for users who cannot use Tailscale, with an explicit warning that Cloudflare will see image data in transit. It should not be the recommended path.

---

## 4. Design Decisions

### 4.1 Supported Remote Modes

**Allowed:**

| Mode | Description |
|------|-------------|
| Self-hosted Find instance | Another machine the user controls running Find's worker stack |
| Home server / NAS | Raspberry Pi, Synology, TrueNAS, etc. running Find's backend |
| Desktop-as-server | User's gaming PC or workstation used as the ML backend for mobile clients |
| Private VPS | A VPS the user owns and administers |
| Team-internal server | A shared server on a private network the team controls |

**Not allowed (out of scope for this design):**

| Mode | Reason |
|------|--------|
| Project-hosted cloud endpoint | Defeats local-first promise; requires infrastructure maintenance; needs a separate privacy impact assessment |
| Third-party ML APIs | Sends user images to corporations the user has no agreement with |
| Any pre-configured endpoint | Violates non-negotiables #1 and #4 |

A future hosted demo is not precluded, but it is a separate feature requiring separate user consent. It must never process a user's own images under this design.

### 4.2 What Data Is Transmitted Per Feature

When remote mode is enabled, the following data leaves the local device for each processing step:

| Feature | Data Transmitted | Sensitivity |
|---------|-----------------|-------------|
| Object detection (YOLOv10) | Full image bytes (JPEG/PNG) | High — full image content |
| Captioning (Florence-2) | Full image bytes | High — full image content |
| OCR (PaddleOCR) | Full image bytes | High — may include personal/sensitive text visible in the image |
| Image embedding (SigLIP) | Full image bytes during indexing | High — full image content |
| Search query embedding | Search query text only | Medium — may reveal what the user is looking for |
| EXIF extraction | Nothing — always runs locally | N/A |
| Clustering (HDBSCAN) | 768-d SigLIP (ViT-B-16) embedding vectors only (no image files) | Medium — no image file, but vectors encode image content (see §5.3) |

**Key implication:** There is no "safe subset" of the current ML pipeline that transmits zero identifiable image data, except clustering. Every inference step requires image bytes. The UI and consent flow must communicate this clearly.

EXIF data (which can contain GPS coordinates, device serial number, and timestamps) is stripped from images before transmission by default, controlled by `REMOTE_ML_STRIP_EXIF=true`.

### 4.3 Scope of Remote Mode

Remote mode is global (on/off) in v1. Per-image and per-library overrides are deferred:

- Per-image overrides add significant UI complexity and are error-prone.
- Per-library overrides are meaningful only after library management exists as a feature.

The global toggle is a clear, auditable boundary. Finer granularity can follow once the baseline is stable.

### 4.4 Authentication

**Why Immich's zero-auth approach is insufficient for Find:**  
Immich's ML container is explicitly documented as "internal with no security measures." It is designed to be on a trusted internal network. Find's remote mode is explicitly for users reaching across networks — from mobile to desktop, from home to VPS. On those paths, relying on the network alone is insufficient.

**Chosen approach: Static bearer token with minimum entropy**

- The server operator generates a token: `openssl rand -hex 32` (256-bit, 64 hex chars).
- The token is set as `REMOTE_ML_API_KEY` in the server's environment.
- Every request from a Find client includes `Authorization: Bearer <token>`.
- The server rejects all requests without a valid token with HTTP 401.

This mirrors the pattern used by real self-hosted tools (Home Assistant long-lived tokens, Grafana API keys, most NAS APIs) without the complexity of OAuth or mTLS. Security research on API tokens ([Stack Overflow best practices](https://stackoverflow.blog/2021/10/06/best-practices-for-authentication-and-authorization-for-rest-apis/), [self-hosted deployment guide](https://hoop.dev/blog/api-token-management-best-practices-for-self-hosted-deployments)) confirms:

- Tokens must never be passed in URLs (log exposure risk).
- 256-bit entropy is the minimum for a secret that cannot be brute-forced.
- Tokens should be revocable without service restart (future: token stored in DB with revocation support; v1: restart with a new `REMOTE_ML_API_KEY` value).

**What Find does not implement in v1:** Token rotation, expiry, or per-scope tokens. These are improvements for a later iteration.

### 4.5 Network Security Options for Mobile-to-Desktop

Find delegates transport security to user-selected tooling. The options, in recommended order:

**Option 1 — Tailscale Serve (recommended)**

Install Tailscale on both devices. Run `tailscale serve 8000` on the server machine. The Find backend is reachable at `https://hostname.tail1234.ts.net` with automatic TLS provisioned by Tailscale. No port forwarding, no certificate management, encrypted end-to-end by WireGuard. Free for personal use.

From the Tailscale documentation: access is "restricted to authenticated Tailnet members only" and includes "TLS and no reverse proxy configuration required."

**Option 2 — Local network, same WiFi**

Mobile and desktop on the same network. User enters the desktop's LAN IP (e.g., `http://192.168.1.42:8000`). Traffic is unencrypted and confined to the LAN.

Find must display a warning when the configured URL is non-localhost and HTTP:
> "This endpoint is not encrypted. Use HTTPS or a VPN (Tailscale) for connections outside your local network."

**Option 3 — Cloudflare Tunnel (with explicit warning)**

User creates a `cloudflare tunnel` to expose Find's port. Provides a public HTTPS URL without a static IP. Suitable for users who cannot install Tailscale.

Find must display a persistent warning when a Cloudflare Tunnel URL is detected (matching `*.trycloudflare.com` or `*.cfargotunnel.com`):
> "Cloudflare Tunnel is active. Cloudflare decrypts traffic at its edge before forwarding it to your server. Your images are visible to Cloudflare in transit."

**Option 4 — Self-signed HTTPS with certificate pinning**

Deferred. Complex to implement correctly. Tailscale covers the same need with better UX.

---

## 5. Privacy Threat Model

### 5.1 Image Data in Transit

**Threat:** Image bytes sent to the remote server are intercepted by a network observer (ISP, attacker on the same network, MITM proxy).

**Mitigations:**
- Require TLS for any URL that is not `localhost` or `127.0.0.1`. Warn and require override for plain `http://` on non-loopback addresses.
- Document Tailscale as the primary transport path.
- Strip EXIF by default before sending (`REMOTE_ML_STRIP_EXIF=true`). EXIF can contain GPS coordinates, timestamps, and device serial numbers.

**Residual risk:** If the user ignores the HTTP warning and configures an unencrypted public endpoint, images are transmitted in plaintext. Find warns but cannot prevent this.

### 5.2 Server-Side Logging and Retention

**Threat:** The remote server (even user-controlled) may log or store image bytes unintentionally (web server access logs, inference framework debug output, monitoring tools).

**Mitigations:**
- The remote endpoint specification (§7) must state that the server must not persist image bytes beyond the duration of the inference request. This is a requirement for compliant server implementations.
- The consent dialog (§8.2) makes clear the user is responsible for the security of their configured server.

This cannot be technically enforced by the Find client, but non-persistence is a documented requirement for any Find-compatible ML server.

### 5.3 Embedding Reversibility

**Threat:** Find's 768-dimensional SigLIP (ViT-B-16) embeddings are not images, but they are not opaque.

**What the research actually shows:** A August 2025 paper, *LeakyCLIP: Extracting Training Data from CLIP* ([arxiv.org/abs/2508.00756](https://arxiv.org/abs/2508.00756)), demonstrated that CLIP ViT-B-16 embeddings can be inverted to reconstruct images with a **358% improvement in SSIM** over baseline methods, using a combination of adversarial fine-tuning, embedding space alignment, and Stable Diffusion refinement. The attack achieved a 5.68% "Highly Similar" rate on facial image reconstruction from embeddings alone. Critically, the paper found that "even for low-fidelity reconstructions, the metrics can still reliably infer whether an image was included in the training set."

A separate December 2024 paper, *Unlocking Visual Secrets: Inverting Features with Diffusion Priors* ([arxiv.org/abs/2412.10448](https://arxiv.org/abs/2412.10448)), confirms that "feature inversion attacks raise privacy concerns across various domains" for systems that store or process extracted features.

**Implication for Find:** Clustering is the only remote operation that sends only embeddings (not image bytes). It should not be advertised as "privacy-safe" or "no image data." The correct framing is:

> "Only numerical vectors are transmitted — no image files. However, recent research shows these vectors can be used to approximately reconstruct images under certain conditions."

**Mitigation:** This is disclosed in the consent dialog and settings UI. Future mitigation options (differential privacy noise on embeddings before transmission) are out of scope for v1 but worth noting for the research record.

### 5.4 Authentication Token Compromise

**Threat:** The bearer token is stolen from a `.env` file, a compromised device, or an intercepted HTTP request.

**Mitigations:**
- 256-bit token entropy makes brute-force infeasible.
- Never transmit the token over HTTP (enforced by the HTTP warning in §4.5).
- Token is stored only in server-side environment, not in the database or logs.
- Rotation: generate a new token, update `REMOTE_ML_API_KEY`, restart the server. All existing client configs become invalid until updated. (No graceful rotation in v1 — this is acceptable for personal setups.)

### 5.5 Relay/Supply-Chain Attack via Malicious Remote URL

**Threat:** A malicious actor tricks a user into configuring a `REMOTE_ML_URL` that captures their images.

**Mitigations:**
- `REMOTE_ML_URL` is user-configured only. Find never distributes or suggests URLs.
- The consent dialog explicitly says "Only enable this if you control that server."
- This is the same threat surface as any user-configured environment variable.

---

## 6. New Configuration Variables

Additions to `backend/src/find_api/core/config.py` (mirroring the existing `ML_MODE` pattern) and `.env.example`:

```dotenv
# Remote ML Acceleration (disabled by default — leave REMOTE_ML_URL empty for local-only)
REMOTE_ML_URL=
REMOTE_ML_API_KEY=
REMOTE_ML_STRIP_EXIF=true

# Which ML features may use the remote endpoint.
# Comma-separated: embed, caption, detect, ocr, cluster
# All except "cluster" send full image bytes to the remote server.
REMOTE_ML_FEATURES=embed,caption,detect,ocr,cluster
```

`ML_MODE` gains a new allowed value: `remote`. When `ML_MODE=remote` and `REMOTE_ML_URL` is empty, the worker refuses to start and logs:

```text
FATAL: ML_MODE=remote but REMOTE_ML_URL is not set.
Set REMOTE_ML_URL to a reachable Find ML server or change ML_MODE to full or mock.
```

Silently falling back to local mode would be confusing — the operator must be explicit.

---

## 7. Remote ML API Contract

The remote Find instance exposes these endpoints under `/api/ml/`. They are consumed only by other Find instances. Full specification is deferred to the implementation issue, but the design requires:

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `GET /api/ml/health` | GET | None | `{ "status": "ok", "ml_mode": "full", "version": "x.y.z" }` |
| `POST /api/ml/analyze` | POST | Multipart: `image` (bytes, EXIF-stripped if enabled) | `{ caption, objects, ocr_text, text_blocks }` |
| `POST /api/ml/embed` | POST | Multipart: `image` (bytes) + `metadata` (JSON) | `{ "embedding": float[768] }` |
| `POST /api/ml/cluster` | POST | JSON: `{ "embeddings": float[][] }` | `{ "labels": int[], "info": {} }` |

All endpoints except `GET /api/ml/health` require `Authorization: Bearer <token>`. The health endpoint is unauthenticated (used for connection test in the UI).

The server that handles these endpoints is a standard Find backend in `full` ML mode. No new server type is introduced; the existing worker's logic is exposed via these new routes.

**Note on Immich's pattern:** Immich's ML server has no auth and no HTTPS. Find's ML API differs by requiring a bearer token on all write/inference endpoints. This is necessary because Find's remote mode is explicitly designed for cross-network use (unlike Immich's ML container, which is internal-only by design).

---

## 8. mDNS Auto-Discovery (Mobile UX Improvement)

Both iOS (native Bonjour) and Android (NSD API, supported since Android 4.1) support mDNS service discovery. A Find server on the local network can broadcast itself as `_find-ml._tcp` so that the mobile client can offer a list of discovered servers instead of requiring manual IP entry.

This is an optional enhancement to the connection setup UX. The mobile client would show:

> "Found Find server: MacBook-Pro.local (192.168.1.42) — Tap to connect"

Implementation is a separate task. This design notes it as a desirable UX improvement for the local-network connection path.

---

## 9. UI Requirements

### 9.1 Settings Page

A dedicated "Remote Acceleration" section, separated from core ML settings:

```text
┌─ Remote Acceleration ────────────────────────────────────────────────────┐
│                                                                          │
│  Enable remote ML processing    [ OFF ]                                  │
│                                                                          │
│  When enabled, images are sent to the server you specify below for       │
│  ML inference. Only enable this if you control that server.              │
│                                                                          │
│  (fields below appear only when toggle is ON)                            │
│                                                                          │
│  Server URL   [ https://find.my-home-server.ts.net:8000        ]         │
│  API Key      [ ••••••••••••••••••••••••••••••••  ] [Show]              │
│                                                                          │
│  Features to offload:                                                    │
│  [✓] Embeddings (CLIP)   [✓] Captions   [✓] Object detection            │
│  [✓] OCR                 [✓] Clustering                                  │
│                                                                          │
│  ℹ Clustering sends only numerical vectors, not image files.             │
│    Research shows vectors can approximately encode image content.         │
│                                                                          │
│  Strip EXIF before sending  [✓] (recommended — removes GPS, timestamps)  │
│                                                                          │
│  [ Test Connection ]  Last test: ● Connected — Find 0.4.0 / full mode   │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 9.2 First-Enable Consent Dialog

Shown once when the toggle is first turned ON. Not shown again unless settings are reset.

```text
┌─ Enable Remote Processing? ──────────────────────────────────────────────┐
│                                                                          │
│  Remote processing sends your images to the server you configured.       │
│                                                                          │
│  What is sent to your remote server:                                     │
│  • Full image files (for detection, captioning, OCR, and indexing)       │
│  • Search query text (when remote search embedding is enabled)           │
│  • Numerical vectors only for clustering (no image file)                 │
│  • EXIF data is stripped before sending if that option is enabled        │
│                                                                          │
│  What is never sent:                                                     │
│  • Images to any project-hosted or third-party server                    │
│  • Any data without your explicit configuration                          │
│                                                                          │
│  Note: Recent research shows that CLIP/SigLIP vectors — even without     │
│  the original image — can be used to approximately reconstruct images    │
│  under certain conditions.                                               │
│                                                                          │
│  You are responsible for the security of your configured server.         │
│  We recommend Tailscale for encrypted remote connections.                │
│                                                                          │
│                          [ Cancel ]  [ I understand — Enable ]           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

"I understand — Enable" is the only activation path. "OK" is insufficient.

### 9.3 Active Remote Mode Indicators

While remote mode is on:

- **Processing view:** Each image processed remotely shows a `Remote` amber pill badge alongside the existing status indicator.
- **Search bar:** A `Remote` label appears next to the search icon when query embedding is generated remotely. Tooltip: "Your search query is processed on your remote server."
- **Gallery header:** An unobtrusive banner: `Remote acceleration active — [server-url]` with a link to settings.

These indicators must be present in any future mobile client as well.

### 9.4 HTTP Warning

When the configured URL uses `http://` and the host is not `localhost` or `127.0.0.1`:

```text
⚠ Unencrypted connection
  Images will be sent in plaintext over the network.
  Use HTTPS or Tailscale for connections outside your local network.
  [ I understand the risk ]
```

Requires acknowledgment per-session; cannot be permanently dismissed.

---

## 10. What This Design Does Not Include

- **A hosted Find demo or cloud service.** Out of scope. Requires a separate design and privacy impact assessment.
- **Per-image or per-library remote overrides.** Deferred to a later iteration.
- **mTLS certificate management.** Tailscale Serve covers this without requiring implementation in Find.
- **Token rotation without restart.** v1 rotation is: generate new token, restart server. Graceful rotation is a future improvement.
- **Differential privacy on embeddings.** Noted in the research record; out of scope for v1.
- **Mobile app implementation.** This design describes the protocol contract; a mobile app is a separate task.

---

## 11. Answers to the Issue's Open Questions

| Question | Answer |
|----------|--------|
| Should Find support only self-hosted endpoints, or also a hosted demo mode? | Self-hosted only in this design. A hosted demo requires a separate design with separate consent. Immich, Ollama, and PhotoPrism all follow the self-hosted-only pattern for ML inference. |
| What exact data is sent for each remote feature? | Full image bytes for detection, captioning, OCR, and image embedding during indexing. Search query text for query embedding when remote search is enabled. 768-d float vectors only for clustering. EXIF stripped before image transmission if the option is enabled. See §4.2. |
| Can remote processing happen per-library or per-image rather than globally? | Global on/off in v1. Per-granularity overrides deferred — consistent with how Immich handles remote ML (global URL setting, not per-album). |
| How should authentication work for a user-owned backend? | 256-bit bearer token in `Authorization` header, required on all inference endpoints. Network-layer security (Tailscale recommended) provides transport encryption. This is more secure than Immich's zero-auth ML container, appropriate given Find's explicit cross-network use case. |
| How should mobile connect securely to desktop Find? | Tailscale Serve (recommended) — provides HTTPS with auto-provisioned TLS, WireGuard encryption, MagicDNS hostnames. Local LAN as fallback. Cloudflare Tunnel as a documented option with an explicit warning that Cloudflare decrypts traffic at its edge. |

---

## 12. Next Steps

Implementation issues will be opened only after this design is reviewed and accepted by the maintainer (@Abhash-Chakraborty). The anticipated issues are:

1. Add `ML_MODE=remote` and `REMOTE_ML_*` config to `config.py` and `.env.example`
2. Implement EXIF stripping before remote transmission
3. Implement `/api/ml/analyze`, `/api/ml/embed`, `/api/ml/cluster`, `/api/ml/health` on the server-side
4. Route `processors.py` inference through `RemoteMLClient` when `ML_MODE=remote`
5. Add Remote Acceleration settings UI (toggle, URL, API key, feature checkboxes, test connection)
6. Add first-enable consent dialog
7. Add active-mode indicators (processing, search, gallery)
8. Document Tailscale setup for mobile-to-desktop in the contributor docs
9. (Optional) mDNS `_find-ml._tcp` broadcast for local network auto-discovery

---

## Sources

- [Immich Architecture Documentation](https://docs.immich.app/developer/architecture/)
- [Immich Remote Machine Learning Guide](https://docs.immich.app/guides/remote-machine-learning/)
- [Ollama API Introduction](https://docs.ollama.com/api/introduction)
- [PhotoPrism Vision Service Setup](https://docs.photoprism.app/developer-guide/vision/service/setup/)
- [Tailscale: Self-Host a Local AI Stack](https://tailscale.com/blog/self-host-a-local-ai-stack)
- [Tailscale Quickstart](https://tailscale.com/docs/how-to/quickstart)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/tunnel/)
- [Cloudflare Tunnel Privacy & Security Tradeoffs](https://www.pieterdev.com/blog/cloudflare-tunnel/)
- [LeakyCLIP: Extracting Training Data from CLIP (arXiv 2508.00756, Aug 2025)](https://arxiv.org/abs/2508.00756v1)
- [Unlocking Visual Secrets: Inverting Features with Diffusion Priors (arXiv 2412.10448, Dec 2024)](https://arxiv.org/abs/2412.10448)
- [API Token Management Best Practices for Self-Hosted Deployments](https://hoop.dev/blog/api-token-management-best-practices-for-self-hosted-deployments)
- [REST API Authentication Best Practices — Stack Overflow Blog](https://stackoverflow.blog/2021/10/06/best-practices-for-authentication-and-authorization-for-rest-apis/)
- [Android Network Service Discovery (mDNS)](https://developer.android.com/develop/connectivity/wifi/use-nsd)

---

## 13. UX Copy Checklist

This checklist is for implementers building the Remote Acceleration UI described in §12.
Copy strings are derived from §9.2, which remains the single source of truth. Implementers should refer to §9.2 for the canonical wording; this checklist summarizes the required items for convenience.

---

### 13.1 First-Enable Consent Dialog (§9.2)

- [ ] **Dialog title:** `Enable Remote Processing?`
- [ ] **Body — what is sent:**
  > "Remote processing sends your images to the server you configured. Full image files are sent for detection, captioning, OCR, and indexing. Search query text is sent when remote search embedding is enabled. Only numerical vectors are sent for clustering — no image file."
- [ ] **Body — what is never sent:**
  > "Images are never sent to any project-hosted or third-party server. No data is transmitted without your explicit configuration."
- [ ] **Embedding caveat (required):**
  > "Recent research shows that CLIP/SigLIP vectors — even without the original image — can be used to approximately reconstruct images under certain conditions."
- [ ] **Responsibility notice:**
  > "You are responsible for the security of your configured server. Tailscale is recommended for encrypted remote connections."
- [ ] **Cancel button label:** `Cancel`
- [ ] **Confirm button label:** `I understand — Enable`
  - Must not use "OK" or "Enable" alone — the full phrase is required.
- [ ] Consent dialog is shown **once only** on first toggle-on. Not shown again unless settings are reset.

---

### 13.2 Active Remote Mode Indicators (§9.3)

- [ ] **Per-image badge (processing view):** `Remote` — amber pill, shown alongside existing status indicator for every image processed remotely.
- [ ] **Search bar label:** `Remote` — shown next to search icon when query embedding is remote.
- [ ] **Search bar tooltip:** `Your search query is processed on your remote server.`
- [ ] **Gallery header banner:** `Remote acceleration active — [server-url]` — unobtrusive, links to settings.
- [ ] All indicators must also be present in any future mobile client.

---

### 13.3 HTTP (Non-localhost) Warning (§9.4)

Shown when configured URL uses `http://` and host is not `localhost`, `127.0.0.1`, `::1`, or `[::1]`.

- [ ] **Warning title:** `⚠ Unencrypted connection`
- [ ] **Warning body:**
  > "Images will be sent in plaintext over the network. Use HTTPS or Tailscale for connections outside your local network."
- [ ] **Acknowledge button:** `I understand the risk`
- [ ] Warning requires acknowledgment **per session** — cannot be permanently dismissed.

---

### 13.4 Cloudflare Tunnel Warning (§4.5)

Shown when the configured URL matches `*.trycloudflare.com` or `*.cfargotunnel.com`.

- [ ] **Warning body:**
  > "Cloudflare Tunnel is active. Cloudflare decrypts traffic at its edge before forwarding it to your server. Your images are visible to Cloudflare in transit."
- [ ] This warning must be **persistent** while Cloudflare Tunnel URL is configured — not a one-time dismissal.

---

### 13.5 General Implementation Notes

- [ ] No project-hosted endpoint is pre-configured. The URL field must be blank by default.
- [ ] The toggle must be **OFF** by default on every fresh install.
- [ ] URL and API Key fields are only visible when the toggle is ON (§9.1).
- [ ] The clustering info note must read:
  > "Clustering sends only numerical vectors, not image files. Research shows vectors can approximately encode image content."
- [ ] EXIF strip checkbox label: `Strip EXIF before sending` with helper text: `Recommended — removes GPS coordinates, timestamps, and device identifiers.`
