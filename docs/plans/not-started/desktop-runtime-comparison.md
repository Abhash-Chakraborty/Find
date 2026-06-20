# Desktop Runtime: Detailed Comparison & Trade-off Analysis

**Status:** Not started  
**Last reviewed:** 2026-05-28  
**Current implementation status:** This comparison still describes the proposed no-Docker runtime. The current complete app runtime remains Docker/PostgreSQL/Redis/MinIO-based.

**Related Documents:**
- [desktop-runtime-adr.md](./desktop-runtime-adr.md) - Full ADR
- [desktop-runtime-quick-reference.md](./desktop-runtime-quick-reference.md) - Quick reference

---

## 1. Database Layer Comparison

### Current: PostgreSQL + pgvector

| Aspect | Details |
|--------|---------|
| **Process** | Separate system service / container |
| **Installation** | System-level: apt/brew + init, user/role setup, port binding |
| **Dependencies** | `psycopg2-binary`, `pgvector` (requires PostgreSQL dev headers) |
| **Storage** | Multiple files in `/var/lib/postgresql/` |
| **Vector Support** | Native `pgvector` extension (indexed HNSW, exact similarity) |
| **Scaling** | Excellent for multi-user/distributed (replication, connection pooling) |
| **Query Performance** | Sub-100ms for 1M+ embeddings with proper indexing |
| **Backup** | `pg_dump`, WAL archiving, point-in-time recovery |
| **Migration** | Hard to extract/move; requires full dump |

### MVP: SQLite + Vector Extension

| Aspect | Details |
|--------|---------|
| **Process** | Library (SQLite) + optional vector extension module |
| **Installation** | Python stdlib `sqlite3` plus a vector extension package such as `sqlite-vec` |
| **Dependencies** | `sqlite3` (Python stdlib), `sqlite-vec` native extension package |
| **Storage** | Single `.db` file (typically <2 GB for 100k images) |
| **Vector Support** | Emerging: `sqlite-vec` for local vector search; must be validated against Find's pgvector behavior |
| **Scaling** | Single-user/machine only; WAL mode allows concurrent reads |
| **Query Performance** | Sub-500ms for typical gallery (1-10k images); needs profiling for 100k+ |
| **Backup** | Simple file copy; no special tools |
| **Migration** | Easy: export to SQL dump or copy file |

### Comparison: Key Trade-offs

| Factor | PostgreSQL | SQLite | Winner (for Desktop) |
|--------|-----------|--------|---|
| **Setup friction** | Higher (system service) | Lower (file) | SQLite ✓ |
| **Resource usage** | ~200 MB RAM baseline | <50 MB | SQLite ✓ |
| **Portability** | Tied to OS/system | Portable (file) | SQLite ✓ |
| **Concurrency** | Many clients | Single process | PostgreSQL (but not needed for desktop) |
| **Max dataset size** | Very high, production-proven | Large raw DB files are supported, but vector-query performance and write concurrency need profiling | PostgreSQL |
| **Vector quality** | Best-in-class (pgvector) | Emerging (sqlite-vec) | PostgreSQL |
| **Dev tooling** | psql, pgAdmin | sqlite3 CLI, DBeaver | Tie |
| **Long-term maintenance** | Mature, stable | Newer, evolving | PostgreSQL |

**Verdict:** SQLite wins for MVP (lower friction). PostgreSQL migration path available in phase 2 for users who outgrow SQLite.

---

## 2. Object Storage Comparison

### Current: MinIO (S3-Compatible)

| Aspect | Details |
|--------|---------|
| **Process** | Container + separate data volume |
| **Architecture** | S3 API server; multi-tenant capable |
| **Storage** | `/data/` directory (mirrored to volumes) |
| **Access** | HTTP (API) + Console (web UI on port 9001) |
| **Scalability** | Horizontal (multiple servers, erasure coding) |
| **Permissions** | IAM-like (access keys, policies) |
| **Durability** | Erasure coding, replication |
| **Bandwidth** | LAN typical (~100 MB/s local) |
| **Use case** | Multi-tenant, distributed deployments |

### MVP: Local Filesystem

| Aspect | Details |
|--------|---------|
| **Process** | None (direct filesystem) |
| **Architecture** | Simple directory hierarchy |
| **Storage** | `~/.find/objects/{year}/{month}/{hash}.*` |
| **Access** | Direct file I/O via Python `pathlib` |
| **Scalability** | Limited by single filesystem (typical max ~10 TB for ext4) |
| **Permissions** | OS-level (Unix permissions, Windows ACL) |
| **Durability** | Depends on filesystem (ext4, NTFS, APFS) |
| **Bandwidth** | Native speed (~500 MB/s+ for SSDs) |
| **Use case** | Single-machine, local-first |

### Comparison: Key Trade-offs

| Factor | MinIO | Filesystem | Winner (for Desktop) |
|--------|-------|-----------|---|
| **Setup** | Container + health check | Directory creation | Filesystem ✓ |
| **Overhead** | ~500 MB RAM, separate process | None | Filesystem ✓ |
| **Transparency** | Hidden behind S3 API | Users see files directly | Filesystem ✓ |
| **Scalability** | 100s of TB | Filesystem limited (~10 TB) | MinIO |
| **Durability** | Erasure coding | OS filesystem | MinIO |
| **API compatibility** | Full S3 | Proprietary (Python API) | MinIO |
| **Concurrency** | Multi-client safe | File locking required | MinIO |
| **Backup** | S3 tools (aws cli) | Standard copy/rsync | Filesystem ✓ |

**Verdict:** Filesystem wins for MVP (no extra process, transparent). S3 compatibility less important for desktop. Hardlink deduplication possible as optimization later.

---

## 3. Job Queue Comparison

### Current: Redis + RQ (Python Redis Queue)

| Aspect | Details |
|--------|---------|
| **Process** | Redis container + Python RQ worker |
| **Storage** | In-memory (Redis) with optional RDB snapshots |
| **Job state** | queued, started, finished, failed (with retry) |
| **Queuing** | Priority queues: `high`, `default`, `low` |
| **Persistence** | RDB snapshots (async, can lose data) |
| **Scalability** | Multiple workers across machines |
| **Concurrency** | Non-blocking, async by design |
| **Failure recovery** | Can recover from RDB, but not guaranteed |
| **Monitoring** | rq-dashboard, redis-cli |

### Option A: In-Process Queue

| Aspect | Details |
|--------|---------|
| **Process** | No separate process (library) |
| **Storage** | In-memory (lost on restart) or SQLite backend |
| **Job state** | scheduled, running, finished, failed |
| **Queuing** | Single queue or priority-based |
| **Persistence** | SQLite option (durable) |
| **Scalability** | Single process only |
| **Concurrency** | Thread pool or async executors |
| **Failure recovery** | SQLite backend survives restart |
| **Monitoring** | Programmatic API or custom dashboard |

### Option B: SQLite-Backed Queue (Custom)

| Aspect | Details |
|--------|---------|
| **Process** | No separate process (library) |
| **Storage** | SQLite job table (durable) |
| **Job state** | queued, running, completed, failed |
| **Queuing** | Flexible (any SQL-based priority) |
| **Persistence** | Guaranteed (ACID transactions) |
| **Scalability** | Single process (concurrent workers via threads) |
| **Concurrency** | Thread pool; WAL mode for concurrent reads |
| **Failure recovery** | Perfect (job state in DB) |
| **Monitoring** | SQL queries or custom admin UI |

### Comparison: Key Trade-offs

| Factor | Redis + RQ | In-process queue | SQLite Queue | Winner (for Desktop) |
|--------|-----------|-----------|---|---|
| **Setup** | Container + deps | Python package | Python package | SQLite ✓ |
| **Resource** | ~100 MB RAM (Redis) | Minimal | Minimal | SQLite/custom queue ✓ |
| **Persistence** | Configurable | Optional | Guaranteed | SQLite ✓ |
| **Worker scalability** | Distributed | Single process | Single process | Tie |
| **Failure recovery** | Weak (RDB) | Weak (memory) | Strong (transactions) | SQLite ✓ |
| **Operational complexity** | Higher | Lower | Lower | SQLite ✓ |
| **Job introspection** | redis-cli + dashboard | Programmatic | SQL + UI | Tie |
| **Maturity** | Battle-tested | Stable | Less proven | Redis + RQ |

**Verdict:** SQLite-backed queue wins for MVP (durable, simple, no extra process). Existing RQ logic can be ported or simplified.

---

## 4. Process Supervision & Lifecycle

### Current: Docker Compose

| Aspect | Details |
|--------|---------|
| **Supervisor** | docker-compose orchestrator |
| **Startup** | `docker compose up --build` (parallel container start) |
| **Health checks** | Healthcheck directives in compose file |
| **Restart policy** | `restart: unless-stopped` |
| **Logging** | `docker compose logs` (stdout/stderr) |
| **Shutdown** | `docker compose down` (signals containers, waits) |
| **Process isolation** | Each container is separate OS process |
| **Crash recovery** | Compose restarts failed containers |

### MVP: Tauri Rust Shell

| Aspect | Details |
|--------|---------|
| **Supervisor** | Custom Tauri app (Rust) |
| **Startup** | Sequential (validate → init DB → start worker → start API → probe) |
| **Health checks** | HTTP probes to `/health` + process status checks |
| **Restart policy** | Programmatic restarts (3x backoff) |
| **Logging** | Files + in-memory buffer (rotated) |
| **Shutdown** | Rust signal handlers + graceful termination |
| **Process isolation** | API + worker as child processes (or threads) |
| **Crash recovery** | Restart failed services, show error UI |

### Comparison: Key Trade-offs

| Factor | Docker Compose | Tauri Shell | Winner (for Desktop) |
|--------|--------|-----------|---|
| **Setup** | Docker installation required | Single executable | Tauri ✓ |
| **Overhead** | ~1 GB base images | ~50 MB installer | Tauri ✓ |
| **Cross-platform** | Good (Linux, macOS, Windows) | Good (all three) | Tie |
| **Update model** | Rebuild images | Auto-updater | Tauri ✓ |
| **User familiarity** | Docker users only | Desktop app users | Tauri ✓ |
| **Process control** | Good (compose) | Better (direct) | Tauri ✓ |
| **Logging visibility** | `docker logs` | File + UI | Tie |
| **Resource efficiency** | Heavier (containers) | Lighter (processes) | Tauri ✓ |
| **Maturity** | Very mature | Newer framework | Docker Compose |

**Verdict:** Tauri shell wins for MVP (no Docker, better UX, lighter). See [desktop-tauri-vs-electron-adr.md](../partial/desktop-tauri-vs-electron-adr.md) for detailed framework analysis.

---

## 5. Configuration & Secrets

### Current: Docker .env + docker-compose.yml

| Aspect | Details |
|--------|---------|
| **Format** | `KEY=value` env file + YAML compose file |
| **Location** | Root directory (`.env`) |
| **User customization** | Edit `.env` or pass to docker-compose |
| **Secrets handling** | Env vars (not ideal for sensitive data) |
| **Validation** | Manual or scripted |

### MVP: JSON Config + Defaults

| Aspect | Details |
|--------|---------|
| **Format** | JSON (`~/.find/config.json`) |
| **Location** | User data directory (`~/.find/`) |
| **User customization** | Edit JSON in text editor or settings UI |
| **Secrets handling** | OS keychain (macOS), Credential Manager (Windows), pass (Linux) |
| **Validation** | Schema validation + UI feedback |

### Comparison: Key Trade-offs

| Factor | Docker .env | JSON Config | Winner (for Desktop) |
|--------|-----------|-----------|---|
| **User familiarity** | Technical | General desktop users | JSON ✓ |
| **Discoverability** | Hidden in root | In standard data dir | JSON ✓ |
| **Safe defaults** | Minimal | Sensible | JSON ✓ |
| **Override mechanism** | Env vars + file | Settings UI | JSON ✓ |
| **Secrets security** | Poor (plaintext) | OS keychain | JSON ✓ |
| **Validation** | Manual | Automated | JSON ✓ |

**Verdict:** JSON config with safe defaults wins for MVP. No need for users to learn env vars.

---

## 6. Summary: Desktop MVP Stack

```text
┌─────────────────────────────────────────────────────────┐
│  Find Desktop App (Tauri Shell)                         │
│  ├─ Process Supervisor                                  │
│  ├─ Auto-updater                                        │
│  └─ System Tray / Window Manager                        │
└────────────┬────────────────────────────────────────────┘
             │
      ┌──────┴─────────┬────────────────┬─────────────────┐
      │                │                │                 │
      v                v                v                 v
  ┌────────────┐  ┌──────────────┐ ┌──────────────┐  ┌──────────┐
  │ SQLite DB  │  │ Filesystem   │ │ Worker       │  │ FastAPI  │
  │            │  │ Storage      │ │ (Thread/     │  │ API      │
  │ ~1 GB      │  │              │ │  Process)    │  │ Process  │
  │            │  │ ~/.find/     │ │              │  │          │
  │ app.db     │  │ objects/     │ │ Job Queue    │  │ Port     │
  │            │  │              │ │ (SQLite)     │  │ dynamic  │
  └────────────┘  └──────────────┘ └──────────────┘  └──────────┘
```

---

## 7. Risk Analysis & Mitigation

### Performance Risks

**Risk: SQLite becomes bottleneck at 10k+ images**
- **Impact:** Search/gallery operations slow down
- **Mitigation:** 
  - Profile query performance early in phase 2
  - Index embeddings and clustering results
  - Document PostgreSQL migration path
  - Offer opt-in PostgreSQL for power users

**Risk: Filesystem I/O contention during concurrent indexing**
- **Impact:** Slow uploads or search while worker is writing
- **Mitigation:**
  - Batch inserts in worker
  - Use separate I/O scheduler for heavy operations
  - Implement job queuing to control concurrency

### Data Integrity Risks

**Risk: SQLite corruption if app crashes mid-write**
- **Impact:** Loss of recent embeddings or metadata
- **Mitigation:**
  - Use WAL (Write-Ahead Logging) mode by default
  - Implement transaction checkpointing in worker
  - Regular database backups (daily in `~/.find/backups/`)

**Risk: Filesystem storage inconsistency (orphaned files)**
- **Impact:** Disk usage grows; missing images in gallery
- **Mitigation:**
  - Implement garbage collection job (daily)
  - Cross-reference filesystem files with DB
  - Log cleanup operations for debugging

### Operational Risks

**Risk: User deletes `~/.find` directory while app is running**
- **Impact:** App crashes or data loss
- **Mitigation:**
  - Validate directory existence at health check
  - Offer recovery UI (restore from backup or start fresh)
  - Lock file mechanism to prevent concurrent access

**Risk: Logs fill partition and cause silent failure**
- **Impact:** App fails to write logs; user unaware of issues
- **Mitigation:**
  - Daily log rotation (7-day retention)
  - Disk usage warning at 80%
  - Manual cleanup option in settings

### Migration Risks

**Risk: PostgreSQL → SQLite schema mapping is incomplete**
- **Impact:** Data loss or corruption during migration
- **Mitigation:**
  - Implement converter in phase 2 (not MVP)
  - Test migration with real datasets
  - Provide rollback option

---

## 8. Validation & Testing Checklist

### Phase 2 (Prototype)

- [ ] SQLite vector extension integration (PoC: `sqlite-vec`)
- [ ] Filesystem storage backend implementation
- [ ] SQLite-backed job queue (durable, simple, no extra process)
- [ ] Tauri shell process supervision (startup, health, shutdown)
- [ ] Configuration layer (defaults, overrides, validation)
- [ ] Logging (file rotation, redaction, privacy)

### Phase 3 (Integration)

- [ ] End-to-end flow: upload → index → search → cluster
- [ ] Stress test: 1k images, 100 concurrent uploads, background clustering
- [ ] Performance profiling: search latency, model load, disk I/O
- [ ] Cross-platform testing: Windows, macOS, Linux
- [ ] Crash recovery: worker crash, API crash, DB corruption
- [ ] Graceful shutdown: verify no data loss

### Phase 4 (Release)

- [ ] Installer packaging (Windows MSI, macOS DMG, Linux AppImage)
- [ ] Auto-updater flow (signed releases, rollback)
- [ ] First-time user experience (model download, gallery load)
- [ ] User feedback collection (form in About section)

---

## 9. Adoption Decision Tree

```text
Start
  │
  ├─ Do you want to run Find on desktop?
  │   ├─ YES: Use desktop MVP (SQLite + filesystem + Tauri)
  │   │       (after ADR acceptance and prototype work)
  │   │
  │   └─ NO: Stay on Docker web stack
  │          (Current option, stable)
  │
  └─ Do you have 10k+ images or need PostgreSQL-level scalability?
      ├─ YES: Migrate to PostgreSQL (phase 2, guided migration)
      │       (Tools provided; not implemented yet)
      │
      └─ NO: Desktop MVP is sufficient
             (No migration needed)
```

---

## 10. Questions for Stakeholders

1. **Database:** Is SQLite + `sqlite-vec` acceptable for MVP, or should desktop mode keep PostgreSQL + pgvector longer?
2. **Storage:** Are users comfortable with transparent filesystem storage? Any concerns about direct file access?
3. **Queue:** Is a custom SQLite-backed queue acceptable, or should the desktop prototype keep Redis/RQ as a managed sidecar until the queue rewrite is proven?
4. **Logging:** Is privacy-first logging approach acceptable (local files, no auto-reporting)?
5. **Timeline:** What prototype milestone should follow ADR acceptance, and which implementation epic should start first?

---

## Appendix: References & Further Reading

- [sqlite-vec GitHub](https://github.com/asg017/sqlite-vec)
- [sqlite-vss GitHub](https://github.com/asg017/sqlite-vss) - older extension useful as background reading, not the preferred MVP path
- [Tauri Documentation](https://tauri.app/)
- [Python RQ Documentation](https://python-rq.org/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)
- [PostgreSQL pgvector](https://github.com/pgvector/pgvector)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
