# Parity Matrix & Sequencing (Phase 1.2)

Consolidated from the eight Phase 1.1 discovery lanes. Source detail lives in
`lane-*.md` alongside this file. This is the single overview that orders Phase 3–8 work.

Legend: **have** = Find already does it · **partial** = exists but incomplete · **missing** = greenfield.

## C.1 Feature parity matrix

| Feature | Reference | Find today | Status | Lane | Effort |
|---|---|---|---|---|---|
| Justified grid layout | yes | fixed CSS grid, uniform rows | **missing** | A | L |
| Virtualized rendering | yes (variable-height, owns scroll) | `virtualized-grid.tsx`, uniform-row, rides window | **partial** | A | M |
| Date-scrubber scrollbar | yes | none | **missing** | A | L |
| Segment/bucket hover preview | yes | none | **missing** | A | M |
| Time-bucket data model | `/timeline/buckets` + `/timeline/bucket` | offset/page `/gallery` | **missing** | A/E | L |
| Albums (CRUD, cover, ordering) | yes | none | **missing** | B | L |
| Album membership + roles | owner/editor/viewer | none | **missing** | B | M |
| Shared links (expiry/password/perms) | yes | none | **missing** | B | L |
| Partner sharing | yes (directional) | none | **missing** | B | M |
| Archive | `visibility` enum | none | **missing** | C | S |
| Favorites | `isFavorite` | exists as `liked` | **have** | C | — |
| Trash + restore (soft delete) | `deletedAt` + purge | hard delete only | **missing** | C | M |
| Asset viewer (zoom/pan/keyboard) | full viewer | metadata dialog only | **missing** | D | L |
| Progressive image loading | thumbhash→thumb→preview→original | single resolution | **missing** | D | M |
| Slideshow | yes | none | **missing** | D | M |
| Casting | Google Cast SDK | none | **defer** | D | — |
| ONNX runtime + EP fallback (CPU) | yes | PyTorch, USE_GPU bool | **partial** | F | M |
| CPU-light model variants | buffalo_s, ViT-B-32 | antelopev2, SigLIP B-16 | **partial** | F | M |
| Semantic search / clustering / OCR / captioning | partial | **yes (Find's niche)** | **have** | F | keep |
| Settings panel UI | full | none | **missing** | G | M |
| Hardware-accel toggle (Auto/GPU/CPU) | EP selection | `USE_GPU` env bool | **partial** | G | M |
| Settings persistence API | yes | `/config` read-only | **partial** | G | M |
| Desktop (Tauri) | n/a (Electron-free) | `src-tauri/` shell exists | **partial** | H | S–M |
| Native mobile | Flutter app | none | **missing/defer** | H | XL |

## C.2 The one contract everything hangs off — Timeline buckets

Both Lane A and Lane E flag this as the long pole. Frontend Phase 3 cannot start until it exists.

- `GET /timeline/buckets` → `[{ timeBucket: "YYYY-MM-DD", count: int }]` (month granularity),
  filtered by the same scoping as the gallery (not archived, not trashed) plus optional
  `isFavorite`, `albumId`, `personId`, `visibility`, `order`.
- `GET /timeline/bucket?timeBucket=YYYY-MM-DD` → columnar parallel arrays
  (`id[], ratio[], thumbhash[], isFavorite[], isArchived[], isTrashed[], localDateTime[]`, …).
  Columnar keeps payloads small for large months — important for low-end clients.

The per-asset `ratio` (aspect) + `thumbhash` are what let the justified grid lay out and
blur-up **before** any thumbnail loads. Find's `media` table must expose both.

## C.3 Asset-state columns (gates the gallery query)

Add to `media`:
- `is_archived BOOLEAN NOT NULL DEFAULT false` (indexed)
- `deleted_at TIMESTAMPTZ NULL` (indexed)
- (favorites already exist as `liked`)

**Scoping rule** — every list surface (gallery, search, timeline buckets, counts/stats) must adopt:
- main timeline / search: `NOT hidden AND deleted_at IS NULL AND is_archived = false`
- archive view: `is_archived AND deleted_at IS NULL`
- trash view: `deleted_at IS NOT NULL`

This is the top correctness/leak risk: a surface that forgets a predicate shows trashed/archived
assets where it shouldn't.

## C.4 Security must-haves (Lane B)

- Shared-link passwords **hashed** (reference compares plaintext — do not copy that).
- Shared-link `key` unguessable (CSPRNG), all public access scoped to exactly the linked
  album/assets, never the owner's full library.
- `expiresAt`, `allowDownload`, `showExif` enforced server-side, not just hidden in UI.
- Every sharing/auth change gets `/security-review` before merge (§5).

## C.5 Recommended build sequence

Dependency-ordered. Earlier unblocks later.

1. **Backend foundation (Phase 4.1 + 3.1).** Add `is_archived`/`deleted_at` to `media`,
   adopt the scoping rule everywhere, ship the timeline-bucket endpoints with the `ratio`/`thumbhash`
   columns. *This is the contract Phase 3 consumes — do it first.* Alembic migration + tests.
2. **Asset-state APIs (Phase 4.4).** archive/unarchive, trash/restore, empty-trash, favorite
   (wire existing `liked`). Tests.
3. **Design system (Phase 2).** Verbatim asset copy + React primitives, in parallel with 1–2.
4. **Timeline UI (Phase 3.2/3.3).** Justified grid (virtualized) + date scrubber against the
   Phase 1 contract.
5. **Viewer + slideshow (Phase 3.4).** Progressive loading discipline.
6. **Albums + sharing (Phase 4.2/4.3 + UI).** Sharing needs the security review.
7. **Settings panel + hardware-accel (Phase 5).** ONNX EP fallback, capability report, tri-state toggle.
8. **ML alignment (Phase 7).** ONNX session layer + CPU-light variants behind Find's ML interface.
9. **Selective Rust (Phase 6).** Only measured hotspots.
10. **Desktop/mobile foundations (Phase 8).** Tauri static-export first (cheap); RN+Expo mobile spike later.

## C.6 YAGNI exclusions (explicitly out of scope unless re-proposed)

Casting; FFmpeg/transcode admin settings; SMTP; DB-backup UI; storage-template engine; OAuth
provider config; map view; the reference `activity` (likes/comments) table (defer until albums ship);
full background mobile auto-backup. Each can be re-added via a `> PROPOSED:` note per §5.
