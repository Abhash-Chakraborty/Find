# Desktop Runtime Design - Quick Reference

**Status:** Not started  
**Last reviewed:** 2026-05-28  
**Current implementation status:** This is still a reference for the proposed no-Docker desktop runtime. The full SQLite/filesystem/SQLite-queue runtime has not landed.

**Full ADR:** [desktop-runtime-adr.md](./desktop-runtime-adr.md)

---

## Executive Summary

Find needs to run on desktop without Docker, PostgreSQL, Redis, or MinIO knowledge. This ADR proposes replacing Docker services with lightweight embedded alternatives while maintaining the local-first privacy guarantee.

---

## TL;DR - MVP Stack

| Component | Current (Docker) | Desktop MVP | Why |
|-----------|------------------|-------------|-----|
| Database | PostgreSQL + pgvector | **SQLite + vector extension candidate** | Single file, no separate process, subject to `sqlite-vec` proof of concept |
| Object Storage | MinIO (S3-compatible) | **Local filesystem** | Transparent, simple, users can browse in file manager |
| Job Queue | Redis + RQ | **SQLite-backed queue** | Eliminates another container while preserving job state |
| Supervisor | docker compose | **Tauri Rust shell** | OS-native, deterministic process control, better UX |
| Configuration | .env + docker-compose | **~/.find/config.json** | Standard desktop app, no need for users to learn env vars |

---

## Key Decisions

### ✅ Database: SQLite + Vector Extension
- **Single-file database:** No installation, init scripts, or user/role setup needed
- **Vector search:** Prototype `sqlite-vec`; keep PostgreSQL + pgvector as fallback if feature parity or performance is not acceptable
- **Schema compatibility:** Existing SQLAlchemy ORM needs light wrapper for vector queries
- **Future proof:** Can migrate to PostgreSQL later if needed

### ✅ Storage: Filesystem
- **Structure:** `~/.find/objects/{year}/{month}/{hash}.jpg`
- **No S3 API needed:** Direct filesystem operations via Python `pathlib`
- **User transparent:** Users can see/backup images directly in file manager
- **Garbage collection:** Background cleanup job removes orphaned files

### ✅ Job Queue: SQLite-backed
- **Persistence:** Job state stored in SQLite, survives restart
- **Approach:**
  - Custom SQLite job table for durable queued/running/completed/failed states
  - In-memory queues only for tests or throwaway development, not the desktop MVP
- **Worker mode:** Can run in-process thread or separate Python process

### ✅ Process Lifecycle: Tauri Shell
- **Startup:** Validate data dir → init DB → start worker → start API → wait for health → show UI
- **Health checks:** Every 10s (API `/health`, worker status, disk space)
- **Graceful shutdown:** Worker finishes current job → API closes → DB disconnects → exit
- **Crash recovery:** Restart failed services up to 3x with backoff

### ✅ Logging & Privacy
- **Local files:** `~/.find/logs/{api.log, worker.log, shell.log, errors.log}`
- **Redaction:** Remove full paths, user names, sensitive data from logs
- **User-controlled:** View logs from UI, no auto-reporting
- **Rotation:** Daily, 7-day retention by default

---

## Data Directory Layout

```text
~/.find/
├── app.db              # SQLite database (metadata, embeddings, jobs)
├── objects/            # Image storage organized by date/hash
├── models/             # Cached ML models (yolo, florence, paddleocr, etc.)
├── logs/               # Application logs (api, worker, shell, errors)
├── config.json         # User settings (GPU mode, log level, worker threads)
└── backups/            # Daily auto-backups (phase 2)
```

---

## Startup Flow

```text
User clicks Find app
  ↓
Tauri shell validates data dir (~/.find)
  ↓
SQLite DB initialized (schema migration if first run)
  ↓
Worker thread/process starts (connects to job queue)
  ↓
FastAPI server starts on 127.0.0.1, preferring port 8000
  ↓
Wait for /health probe (30s timeout)
  ↓
Frontend renders (built Next.js bundle)
  ↓
Gallery loads, app is interactive
```

**Target:** <5s with cached models, ~15s on first run (model download)

---

## Shutdown Flow

```text
User quits app
  ↓
Tauri shell marks worker as "stopping"
  ↓
Worker finishes current job or checkpoints (30s timeout)
  ↓
API server closes (no new requests, finish pending responses)
  ↓
Database connections close
  ↓
App exits cleanly
```

**Target:** <5s under normal conditions

---

## Migration Path: Docker → Desktop

### For New Users
- Start with desktop MVP directly (no Docker needed)

### For Existing Docker Users
- **Phase 1 (MVP):** Continue using Docker stack; desktop is separate
- **Phase 2:** Provide PostgreSQL → SQLite converter for schema and data
- **Phase 3:** Batch export tool (PostgreSQL → SQLite + filesystem objects)

### Data Portability
✓ Export from Docker: `pg_dump`, copy MinIO objects
✓ Import to Desktop: Converter script, copy objects to `~/.find/objects/`
✓ Reverse (Desktop → Docker): Export SQLite to PostgreSQL SQL, copy objects

---

## Identified Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| SQLite slow under heavy indexing | API sluggish during embedding writes | WAL mode, connection pooling, batch inserts |
| Model cache fills disk | User runs out of space | Warn at 80% usage, implement cache cleanup |
| Worker crash mid-job | Incomplete embeddings | Checkpoint job state, restart and resume |
| Large gallery (10k+) slow search | Unacceptable latency | Index embeddings, profile queries, PostgreSQL option later |
| Cross-platform process management | Windows/Linux/macOS inconsistency | Test all platforms, use cross-platform Rust libs |
| DB corruption if deleted while running | Data loss or crash | Validate DB at health check, recover/restart |
| Logs fill partition | Silent failure | Daily rotation, 7-day retention, manual cleanup option |
| SQLite vector performance | Future growth bottleneck | Benchmark `sqlite-vec`, document path back to PostgreSQL, build converter in phase 2 |

---

## Acceptance Criteria (ADR Review)

The ADR is accepted when maintainers confirm:

- [ ] Research questions answered (database, storage, queue, lifecycle, logging)
- [ ] MVP stack is clearly defined
- [ ] Process lifecycle plan is complete
- [ ] Migration risks are identified and mitigated
- [ ] Data privacy/logging approach is acceptable
- [ ] Trade-offs are well-reasoned and documented
- [ ] Community feedback has been gathered

---

## Next Steps (After ADR Acceptance)

1. **Phase 2 Implementation Epics:**
   - `desktop-storage-backend`: Filesystem storage implementation
   - `desktop-database`: SQLite schema & migrations
   - `desktop-queue`: Job queue refactor
   - `desktop-shell`: Tauri supervisor & process management

2. **Parallel Work:** Tauri shell architecture spike

3. **PoC Target:** After ADR acceptance and implementation epics are created

4. **Beta Release:** With opt-in user feedback

---

## Configuration Defaults (No Setup Required)

| Setting | Default Value |
|---------|---|
| `FIND_DATA_DIR` | `~/.find` (auto-resolved by Tauri) |
| `DATABASE_URL` | `sqlite:///{FIND_DATA_DIR}/app.db` |
| `STORAGE_BACKEND` | `local` |
| `QUEUE_BACKEND` | `sqlite` |
| `USE_GPU` | `true` (auto-detect) |
| `ML_MODE` | `full` |
| `LOG_LEVEL` | `info` |
| `API_PORT` | `8000` preferred, fallback to a free localhost port |
| `API_BIND` | `127.0.0.1` only |

Users can override via `~/.find/config.json` for advanced use.

---

## Files & Documentation

- **Full ADR:** [desktop-runtime-adr.md](./desktop-runtime-adr.md) (full design document)
- **Related ADRs:**
  - [desktop-tauri-vs-electron-adr.md](../partial/desktop-tauri-vs-electron-adr.md) - Framework choice
  - [local-first-roadmap.md](../partial/local-first-roadmap.md) - Broader roadmap
  - [mobile-strategy.md](./mobile-strategy.md) - PWA-first mobile approach
- **Implementation reference:** [dependency-policy.md](../../policies/dependency-policy.md)

---

## Questions?

Open a discussion on GitHub or comment on the ADR pull request. This is a design phase—all feedback is welcome before implementation begins.
