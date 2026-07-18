# ADR: Local Desktop Runtime Design (No Docker Required)

- **Status:** Not started
- **Date:** 2026-05-18
- **Last reviewed:** 2026-06-19
- **Owner:** Find maintainers
- **Related:** Issue #43, Roadmap [local-first-roadmap.md](../partial/local-first-roadmap.md), Framework choice [desktop-tauri-vs-electron-adr.md](../partial/desktop-tauri-vs-electron-adr.md)

**Current implementation status:** A Tauri UI prototype exists, but this no-Docker runtime design is not implemented. Find still depends on the Docker/PostgreSQL/Redis/MinIO runtime for the complete local stack.

---

## 1. Context

Find is currently deployed as a Docker-based stack requiring knowledge of PostgreSQL, Redis, RQ, MinIO, and FastAPI. A normal desktop user should not need this operational knowledge to run Find locally.

The desktop runtime must remain **local-first** by default: images, embeddings, metadata, and search indices must stay on the user's machine. The runtime must support the complete Find workflow—upload, index, embed, cluster, and search—without external services.

**Key constraint:** This is a design phase only. Implementation of the runtime services comes after this ADR is accepted.

---

## 2. Goals

1. **Eliminate Docker/Compose requirement** for single-machine desktop usage
2. **Design a manageable runtime** that a user can install and run without container knowledge
3. **Preserve data locality** (no data leaves the user's machine by default)
4. **Support process lifecycle** (start, stop, restart, health checks, graceful shutdown)
5. **Define migration path** from current Docker stack to desktop stack (for existing API / schema)
6. **Recommend logging and telemetry** that respect privacy (no automatic data collection)

---

## 3. Non-goals

- Implementing the desktop shell, installer, or sidecar orchestration (that is phased later)
- Rewriting the FastAPI API, ML pipeline, or schema
- Supporting full distributed deployment in this phase
- Designing cloud-sync or multi-device sync workflows (future phase)
- Implementing background update checks or crash reporting in this ADR

---

## 4. Research Questions & Decisions

### 4.1 Database: PostgreSQL + pgvector → SQLite + Vector Extension

**Question:** Can PostgreSQL + pgvector remain a managed local dependency, or should installer mode use a lighter embedded vector store?

**Research findings:**

- **PostgreSQL full stack:** Requires system PostgreSQL installation, init scripts, user/role setup, and port management. Feasible but adds operational friction for a desktop user.
- **pgvector extension:** Currently requires PostgreSQL. Porting pgvector behavior to SQLite is non-trivial because Find depends on vector similarity search, exact matching baselines, and clustering integration.
- **SQLite + vector extension (recent 2024+ development):** Emerging projects like `sqlite-vec` can provide local vector search without an external database process. `sqlite-vss` is older and less suitable as a default because it is no longer the main active path from the same ecosystem. Compatibility with SQLAlchemy, vector dimensions, filtering, and Find's current search/clustering behavior must be validated with a proof of concept.
- **Hybrid approach:** Use SQLite for MVP to eliminate PostgreSQL dependency. Allow opt-in PostgreSQL for advanced deployments and high-volume scenarios later.

**Decision: Use SQLite with vector extension for desktop MVP**

- **Rationale:**
  - Single-file database eliminates system-level dependency
  - No separate process to launch, monitor, or manage
  - Sufficient for single-user, single-machine indexing workflows
  - Can be migrated to PostgreSQL later if needed (schema migration scripted)
  - Reduces installer complexity and first-run friction

- **Technical approach:**
  - Prototype `sqlite-vec` first via Python bindings, keeping PostgreSQL + pgvector as the fallback if feature parity or performance is not acceptable
  - Wrap vector similarity queries in SQLAlchemy layer (via custom SQL functions)
  - Store metadata, embeddings, clusters, and job state in single `.db` file under user data directory
  - Define schema migration if/when PostgreSQL support is added

- **Acceptance criteria for later implementation:**
  - SQLite can execute all Find queries (search by embedding, similarity, clustering filters)
  - Query performance remains acceptable (<500ms for typical gallery + search)
  - Single-file backup and export mechanisms are straightforward

**SQLite vector spike result (2026-06-19):**

A focused proof of concept now exists at `backend/src/find_api/core/sqlite_vec_poc.py` with tests in `backend/tests/test_sqlite_vec_poc.py`. It validates the basic desktop-mode shape without changing the production Docker/PostgreSQL runtime:

- creates a SQLite database and media metadata table
- loads `sqlite-vec` as an optional local extension
- creates a 768-dimensional vector table matching Find's current embedding size
- inserts media rows and vector blobs
- runs nearest-neighbor vector search
- returns a gallery-style metadata result shape

To run the spike manually:

```bash
cd backend
pip install sqlite-vec
uv run pytest tests/test_sqlite_vec_poc.py -q
```

The tests skip automatically when `sqlite-vec` is not installed because this is still a desktop-runtime spike, not a default backend dependency.

Current limitations:

- It does not replace PostgreSQL + pgvector in Docker mode.
- It does not cover migrations from the existing PostgreSQL schema.
- It does not benchmark larger libraries, concurrent writes, WAL behavior, or index build cost.
- It does not yet validate Find's full hybrid search behavior, filters, clustering joins, or queue interactions.
- It keeps `sqlite-vec` out of the default dependency set until the project decides whether desktop mode should ship it.

Follow-up implementation should only happen after the spike is benchmarked against realistic local libraries and the query abstraction is designed so PostgreSQL and SQLite can coexist cleanly.

---

### 4.2 Object Storage: MinIO → Local Filesystem

**Question:** Can MinIO be replaced with local filesystem object storage for desktop mode?

**Research findings:**

- **MinIO:** S3-compatible object store running in a container. Adds operational overhead, another health check, and persistence management. Overkill for single-user desktop where local filesystem is reliable.
- **Filesystem approach:** Use a local directory (e.g., `~/.find/images/`) as object store. Organize files by hash or UUID. Simple, transparent, and backed by OS filesystem.
- **Trade-offs:**
  - Simplifies deployment and monitoring (no extra process)
  - Filesystem permissions and backups are understood by all users
  - Potential issue: Concurrent access, symlinks, and cleanup. Mitigated by using a separate worker thread and atomic rename operations
  - Loss of S3 compatibility, but Find is not shipping as multi-tenant SaaS initially

**Decision: Use local filesystem with hierarchical directory structure**

- **Rationale:**
  - Eliminates another container and its lifecycle management
  - Object storage interface (get, put, delete) maps directly to filesystem operations
  - Transparent: users can browse images in file manager if needed
  - Supports hard links or copies for deduplication without added complexity

- **Technical approach:**
  - Introduce or extend the storage abstraction around `backend/src/find_api/core/storage.py`
  - Implement `LocalFileSystemStorageBackend` using `pathlib` and atomic operations
  - Organize images by date or hash: `~/.find/objects/{year}/{month}/{hash}.jpg`
  - Implement cleanup and garbage collection via background job
  - Use file-based locking for concurrent upload/download

- **Acceptance criteria for later implementation:**
  - Same logical storage interface in Python layer (get, put, delete, signed/local URL)
  - Concurrent uploads do not cause data loss or corruption
  - Images are retrievable via API and gallery UI without latency regression
  - Backup/export can copy the entire object directory without database dump

---

### 4.3 Job Queue: Redis + RQ → SQLite-backed or In-Process Queue

**Question:** Can Redis/RQ be replaced with an in-process or SQLite-backed job queue for desktop mode?

**Research findings:**

- **Redis + RQ:** In-memory job queue with background worker. Requires Redis process, health check, and connection pooling. Effective for multi-machine deployments but adds overhead for single-user desktop.
- **SQLite-backed queue:** A custom queue table can persist jobs and worker state without a separate Redis instance. Trade-off: no strict ordering or real-time pub/sub, but acceptable for background ML tasks.
- **In-process queue (async task pool):** Use Python's `asyncio` + thread pool for queuing and executing jobs within the same process. Simplest option but loses isolation between API and workers.
- **Hybrid:** Keep RQ for complex retry/error handling logic, but run it in-process with an in-memory or SQLite backend instead of Redis.

**Decision: Use a custom SQLite-backed queue with in-process or separate worker mode**

- **Rationale:**
  - Eliminates Redis container and its process management
  - SQLite persistence ensures jobs survive process restart
  - Sufficient for background indexing and clustering on desktop
  - Existing RQ logic can be ported or simplified for single-machine use

- **Technical approach:**
  - Evaluate a custom job table in SQLite (id, status, task name, args, retries, created_at, started_at, completed_at)
  - Treat in-memory queues only as test/dev helpers, not the desktop MVP, because they do not survive restart
  - Define job states: queued, running, completed, failed
  - Implement a simple polling-based worker over the SQLite job table
  - Wrap enqueue/dequeue operations in transaction-safe SQLite calls
  - Worker can run in-process or in a separate Python thread/process

- **Acceptance criteria for later implementation:**
  - Jobs are enqueued via same `find_api.workers.enqueue_job()` interface
  - Worker processes background indexing (caption extraction, embedding generation, clustering)
  - Failed jobs are retried and can be inspected via admin UI or logs
  - Job queue does not block the API during heavy processing
  - Existing RQ-based job tests can be adapted with minimal changes

---

### 4.4 Process Lifecycle: Start, Stop, Health Check

**Question:** How should the desktop shell start, stop, and health-check the backend and worker?

**Research findings:**

- **Current Docker setup:** Compose orchestrates containers with health checks. Tauri supervisor needs similar capability in Rust.
- **Process lifecycle:** API server, worker, database connection pool, and object storage must start in correct order and shut down gracefully.
- **Health checks:** API `/health` endpoint, worker availability, database connectivity, job queue status.
- **Graceful shutdown:** In-flight jobs should be allowed to finish or be checkpointed; connections should close cleanly.

**Decision: Tauri shell owns process supervision with startup sequencing and health checks**

- **Rationale:**
  - Rust supervisor has deterministic process control and can manage child lifetimes
  - Aligns with ADR on desktop framework choice (Tauri)
  - Health checks are simple HTTP/socket probes; easily implemented in Rust

- **Technical approach:**

  **Startup sequence (in order):**
  1. Resolve app data directory (OS-specific: `~/.find` on Linux/macOS, `%APPDATA%\Find` on Windows)
  2. Initialize SQLite database file if missing (run migrations)
  3. Start in-process or separate worker thread/process
  4. Start FastAPI uvicorn server on `127.0.0.1`, preferring port `8000` but falling back to a free localhost port if needed
  5. Wait for API `/health` endpoint to respond (exponential backoff, 30s timeout)
  6. Render frontend / initialize IPC bridge
  7. Periodically probe health status (every 10s)

  **Health check probes:**
  - API: `GET /health` → expect `{"status": "healthy"}`
  - Database: Test SQLite connection and schema version
  - Worker: Query pending job count and last job completion time
  - Disk: Check free space in app data directory

  **Graceful shutdown:**
  1. Frontend signals intent to quit
  2. Tauri supervisor marks worker as "stopping"
  3. Worker finishes current job or checkpoints state (30s timeout)
  4. API server closes cleanly (stop accepting new requests, finish pending responses)
  5. Database connections close
  6. Exit with code 0

  **Crash recovery:**
  - If API crashes, supervisor restarts it (up to 3 times, then show error)
  - If worker crashes, restart in background (not critical for browsing)
  - If SQLite is corrupted, show recovery UI or restore from backup

- **Acceptance criteria for later implementation:**
  - Rust supervisor can fork and manage child processes
  - Health checks are integrated into Tauri's system tray or main window status bar
  - Worker can be toggled on/off via UI (useful for resource-constrained machines)
  - Shutdown completes in <5s under normal conditions
  - Crash scenarios are logged and do not leave the app in an inconsistent state

---

### 4.5 Logs and Crash Reporting (Privacy-Preserving)

**Question:** How do logs and crash reports work without leaking private data?

**Research findings:**

- **Current Docker setup:** Logs go to stdout/stderr and are visible in `docker logs` or the compose output.
- **Desktop expectations:** Users expect logs in a file, accessible from the UI (developer tools / about section).
- **Privacy concern:** Logs may inadvertently contain image filenames, metadata, or user paths. Crash reports must not auto-upload without consent.
- **Best practice:** Logs are written locally; users can opt into sharing crash reports; sensitive fields are redacted.

**Decision: Local file logging with user-controlled opt-in for telemetry**

- **Rationale:**
  - Logs stay on user's machine by default
  - No automatic data collection or external HTTP calls
  - Users can manually export logs for debugging if they choose to share
  - Transparent: users know where logs are and can delete them

- **Technical approach:**

  **Log storage:**
  - API logs: `~/.find/logs/api.log` (rotated daily, 7-day retention by default)
  - Worker logs: `~/.find/logs/worker.log` (rotated daily)
  - Tauri shell logs: `~/.find/logs/shell.log` (app startup, process lifecycle, IPC events)
  - Format: JSON lines for easy parsing, or human-readable text with structured fields

  **Log redaction:**
  - Remove full file paths (use relative or hashed paths in logs)
  - Redact user home directory names in paths
  - Log embedding/model names but not full vectors or binary data
  - Log error tracebacks but not variable values (use `logging.exception()` carefully)

  **Error and crash logs:**
  - Catch unhandled exceptions in API, worker, and shell
  - Log to dedicated `~/.find/logs/errors.log`
  - Include stack trace, timestamp, and reconstructable context
  - Do NOT auto-report to remote server

  **User-facing log access:**
  - Add "View Logs" button in Find's settings/about screen
  - Open log folder in file manager or show in-app log viewer
  - No data sent outside the machine unless user explicitly chooses to share

  **Telemetry opt-in (future phase):**
  - If crash reporting is added later, it must be explicitly opt-in
  - Crash report form should allow user to review/edit before sending
  - Report should NOT include images, custom filenames, or full paths by default
  - Include only: OS, app version, error type, stack trace (generic), reproducible steps

- **Acceptance criteria for later implementation:**
  - Logs are human-readable and machine-parseable
  - Sensitive paths and filenames do not appear in logs
  - Log files are readable from UI without additional tools
  - Log rotation does not lose recent data or consume excessive disk space
  - No HTTP requests to external services for logging without explicit user consent

---

## 5. Desktop Runtime Stack Comparison

| Aspect | Current Docker | Desktop MVP | Trade-off |
|--------|--------|--------|--------|
| **Database** | PostgreSQL + pgvector (container) | SQLite + vector extension (file) | ✓ Simpler, ✗ Upgrade path to PostgreSQL later |
| **Object Storage** | MinIO (container) | Filesystem (~/.find/objects/) | ✓ Transparent, ✗ No S3 compatibility initially |
| **Job Queue** | Redis + RQ (containers) | SQLite/in-process queue | ✓ Single process, ✗ No distributed jobs |
| **ML Dependencies** | In containers (torch, transformers, etc.) | Same Python install, local model cache | ✓ Shared, ✗ Model storage is user's responsibility |
| **Monitoring** | docker compose ps, docker logs | Tauri supervisor + status endpoint | ✓ OS-native, ✗ Less visibility into internals |
| **Updates** | Rebuild containers | Tauri updater (signed releases) | ✓ Familiar to desktop users, ✗ Release workflow complexity |
| **Install footprint** | Docker + compose + images (~2–5 GB first run) | Python runtime + models (~4–6 GB) | Similar, but no container overhead |

---

## 6. Migration Path: Docker → Desktop

### 6.1 Schema Compatibility

The existing Find API uses FastAPI + SQLAlchemy. Schema migration is possible but requires careful planning:

**Near-term (MVP): No automatic migration**
- Desktop MVP targets new users or users who can re-import images
- Users running Docker stack today can continue using Docker
- Future phase can add schema converter tools

**Medium-term (Phase 2): Schema migration utilities**
- PostgreSQL → SQLite schema export tool (SQL dump → SQLite schema)
- Data migration script: export embeddings + metadata from PostgreSQL, import into SQLite
- User-initiated, not automatic (respects data ownership)

### 6.2 Data Portability

Ensure users can:
1. **Export from Docker stack:**
   - PostgreSQL dump: `pg_dump find > backup.sql`
   - MinIO objects: Copy from mounted volume or use S3 client
   - Redis job queue: Serializable job records (for audit, not recovery)

2. **Import to Desktop stack:**
   - Restore SQLite from PostgreSQL dump (via converter)
   - Restore objects to `~/.find/objects/`
   - Job queue starts fresh (background re-indexing if needed)

3. **Reverse (Desktop → Docker):**
   - Export SQLite to PostgreSQL SQL format
   - Copy filesystem objects to MinIO bucket
   - Maintain embedding vectors for zero re-indexing

---

## 7. Process Lifecycle Plan: Detailed

### 7.1 Startup

```text
[User launches Find app]
  ↓
[Tauri shell initializes]
  ├─ Validate app data directory exists (~/.find)
  ├─ Check SQLite database file
  │   └─ If missing, run schema migrations (CREATE TABLE, indices)
  ├─ Start worker (in-process or separate thread)
  │   └─ Connect to SQLite job queue
  ├─ Start FastAPI server (uvicorn on 127.0.0.1, preferred port 8000)
  │   └─ Lifespan event: init_db(), init_storage(), warmup models
  ├─ Wait for /health probe (exponential backoff, 30s limit)
  ├─ Load frontend bundle (Next.js .next/ static files)
  ├─ Initialize frontend ↔ backend IPC bridge
  └─ Show main window, render gallery
```

**Timing target:** <5s from click to interactive UI (cached models), ~15s first-run (model download/cache).

### 7.2 Runtime Monitoring

```text
[Every 10 seconds, background thread in shell]
  ├─ HTTP GET /health → check API status
  ├─ Query job queue: pending count, last completion time
  ├─ Check disk space: warn if <1 GB free
  ├─ Check worker thread/process: restart if dead
  └─ Update UI status indicator (green = healthy, yellow = degraded, red = down)
```

### 7.3 Shutdown

```text
[User quits app or closes window]
  ↓
[Tauri shell signals shutdown]
  ├─ Mark worker state as "stopping"
  ├─ Worker finishes current job or checkpoints (30s timeout)
  ├─ API server: stop accepting new requests, finish pending responses
  ├─ Close database connections (commit/rollback as needed)
  ├─ Exit worker thread/process gracefully
  └─ Shell exits (code 0)
```

**Graceful shutdown target:** <5s under normal conditions; <30s if worker is mid-job.

### 7.4 Recovery from Crashes

| Scenario | Action | User experience |
|----------|--------|---|
| API crashes | Restart (up to 3x), backoff 1s each | Status indicator turns red; brief message on 3rd failure; offer restart UI |
| Worker thread dies | Restart in background | Queued jobs re-attempt; no blocking on UI |
| SQLite corrupted | Show recovery dialog | Offer restore from backup or start fresh (loss of recent data) |
| Model cache missing | Re-download on next indexing job | Delays first image processing; no crash |
| Disk full | Warn and pause uploads | Status message; user must free space |

---

## 8. Data Directory Structure

```text
~/.find/                           # Root app data directory
├── app.db                          # SQLite database (metadata, embeddings, jobs, clusters)
├── objects/                        # Image object storage
│   ├── 2026/01/
│   │   ├── abc123def456.jpg        # Original image
│   │   ├── abc123def456_thumb.jpg  # Thumbnail
│   │   └── ...
│   └── ...
├── models/                         # Cached ML models
│   ├── yolov10.pt
│   ├── florence-2
│   ├── paddleocr_en
│   └── ...
├── logs/
│   ├── api.log                     # API access/error logs
│   ├── worker.log                  # Background job logs
│   ├── shell.log                   # Tauri shell lifecycle logs
│   └── errors.log                  # Crash/exception logs (rotated)
├── config.json                     # User settings (log level, worker threads, model mode)
├── state.json                      # Runtime state (last gallery scroll position, etc.)
└── backups/                        # Auto-backups (optional, phase 2)
    └── app.db.2026-05-18.bak       # Daily database backup
```

---

## 9. Configuration & Environment

**Desktop MVP should not require env var setup.** Defaults are sensible:

| Setting | Default | Type | Purpose |
|---------|---------|------|---------|
| `FIND_DATA_DIR` | `~/.find` | Path | App data root (auto-resolved by Tauri) |
| `DATABASE_URL` | `sqlite:///{FIND_DATA_DIR}/app.db` | URL | SQLite file-based DB |
| `STORAGE_BACKEND` | `local` | Enum | Use filesystem instead of MinIO |
| `QUEUE_BACKEND` | `sqlite` | Enum | Use SQLite job queue |
| `USE_GPU` | `true` (auto-detect) | Bool | Attempt to use NVIDIA/AMD GPU if available |
| `ML_MODE` | `full` | Enum | `full` (real models) or `mock` (for testing) |
| `LOG_LEVEL` | `info` | Enum | `debug`, `info`, `warning`, `error` |
| `API_PORT` | `8000` preferred, fallback to free port | Int | Local API server port. The shell should record the actual bound port and pass it to the UI/runtime config. |
| `API_BIND` | `127.0.0.1` | IP | Localhost only; do not bind to LAN by default. |

Users can override via `~/.find/config.json` for advanced use.

---

## 10. Identified Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **SQLite concurrency under heavy indexing** | Slow API response if worker is writing embeddings | Implement connection pooling; use WAL mode; batch inserts |
| **Model cache bloats disk** | User runs out of space | Implement model cache cleanup; warn at 80% disk usage |
| **Worker crash mid-job** | Incomplete embeddings or corrupted data | Implement job checkpointing; log job state; restart and resume |
| **Large gallery (10k+ images) slows search** | User expects responsive search | Profile query performance; validate SQLite vector extension behavior; offer PostgreSQL export path later if needed |
| **Tauri process management on Windows/Linux differs** | Inconsistent startup/shutdown behavior | Test on all three platforms; use `std::process` for cross-platform process management, and use Unix-only crates such as `nix` only behind platform-specific code |
| **User deletes database while app is running** | Corruption or crash | Validate DB file existence at health check; recover or offer full restart |
| **Logs accumulate and consume disk** | Silent failure if `/logs` fills partition | Implement daily rotation; keep 7-day retention by default; offer manual cleanup |
| **Future PostgreSQL migration not planned** | Stranded users if SQLite hits limits | Document migration path now; build converter tools in phase 2 |

---

## 11. Validation & Testing Strategy

### Phase 1: Design Validation (Now)
- [ ] Review this ADR with project maintainers and community
- [ ] Validate SQLite vector extension compatibility (create PoC with `sqlite-vec`; keep PostgreSQL + pgvector fallback documented)
- [ ] Confirm filesystem storage layout works with existing `find_api.core.storage` abstraction
- [ ] Sketch SQLite-backed queue integration with RQ or custom queue

### Phase 2: Prototype (After ADR acceptance)
- [ ] Build desktop-mode configuration layer (env vars, config.json)
- [ ] Implement `LocalFileSystemStorageBackend`
- [ ] Create SQLite schema and migration runner
- [ ] Port job queue to SQLite-backed persistence
- [ ] Add Tauri shell skeleton with process supervision
- [ ] Test startup/shutdown on Windows, macOS, Linux

### Phase 3: Integration (Tauri shell complete)
- [ ] End-to-end flow: upload → index → search → cluster on desktop
- [ ] Stress test: 1k+ images, health checks, worker crashes
- [ ] Performance profiling: search latency, model load time, disk I/O
- [ ] Installer packaging and auto-update flow

### Phase 4: Release
- [ ] Public beta on GitHub Releases
- [ ] Gather user feedback on startup time, resource usage, stability
- [ ] Document first-time setup and troubleshooting

---

## 12. Acceptance Criteria

This ADR is accepted when:

- [ ] **Design document is complete** and addresses all 5 research questions
- [ ] **Service comparison table** shows clear trade-offs and rationale
- [ ] **MVP runtime path** is defined (SQLite + filesystem + SQLite queue)
- [ ] **Migration risks** are identified and mitigated
- [ ] **Process lifecycle plan** includes startup, monitoring, shutdown, crash recovery
- [ ] **Data directory structure** is finalized and documented
- [ ] **Risks and validation strategy** are reviewed and approved by maintainers
- [ ] **No implementation** has started (this is design-only)
- [ ] **Community feedback** has been gathered via PR comments or discussions

---

## 13. Next Steps (After ADR Acceptance)

1. **Phase 2 kickoff:** Create implementation epics for each component
   - `desktop-storage-backend`: Filesystem storage implementation
   - `desktop-database`: SQLite schema and migrations
   - `desktop-queue`: Job queue refactor
   - `desktop-shell`: Tauri supervisor and process management

2. **Parallel work:** Tauri shell architecture spike (see [desktop-tauri-vs-electron-adr.md](../partial/desktop-tauri-vs-electron-adr.md))

3. **PoC delivery:** Working prototype target after ADR acceptance and implementation epics are created

4. **Community testing:** Beta release with opt-in feedback form

---

## Appendix A: Glossary

- **Local-first:** All data stays on user's machine by default; no required cloud sync or telemetry
- **Embedded vector store:** SQLite with vector similarity (not external database)
- **WAL mode:** Write-Ahead Logging in SQLite; enables better concurrency
- **Graceful shutdown:** Process finishes pending work and closes cleanly instead of being killed
- **Health check:** Probe (HTTP, socket, or process query) to verify a service is running and responsive
- **Sidecar:** Process (API server, worker) managed by parent process (Tauri shell)
- **Job queue:** Persistence layer for asynchronous tasks (uploads, indexing, clustering)

---

## Appendix B: References

- [Installable Local-First Architecture Roadmap](../partial/local-first-roadmap.md)
- [Desktop Framework: Tauri vs Electron ADR](../partial/desktop-tauri-vs-electron-adr.md)
- [Mobile Strategy: PWA First](./mobile-strategy.md)
- SQLite vector extension candidate: [`sqlite-vec`](https://github.com/asg017/sqlite-vec)
- Tauri documentation: https://tauri.app/
- RQ (job queue): https://python-rq.org/
- SQLAlchemy docs: https://docs.sqlalchemy.org/
