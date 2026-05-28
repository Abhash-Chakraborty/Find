# ADR: Provider-Neutral Object Storage Direction for Find

**Status:** Not started

**Last reviewed:** 2026-05-28

**Current implementation status:** The backend still imports and constructs the MinIO SDK client directly in `backend/src/find_api/core/storage.py`, and configuration remains `MINIO_*`-based. No provider-neutral storage abstraction has landed yet.

Related issue: [#64](https://github.com/Abhash-Chakraborty/Find/issues/64)

## Scope

This note evaluates the current storage architecture only from:

- `backend/src/find_api/core/storage.py`
- `backend/src/find_api/core/config.py`
- `docker-compose.yml`
- `docker-compose.light.yml`
- `docs/`

It does not propose a storage migration in this PR. The goal is to document the current coupling, compare realistic options, and recommend an architectural direction that keeps Find local-first.

## Current Architecture

Find currently uses one object-storage integration path:

- `storage.py` imports the MinIO Python SDK directly and creates a module-level `Minio` client.
- `config.py` exposes only `MINIO_*` backend settings.
- Both Compose files define a `minio` service and inject `MINIO_*` variables into the API and worker.
- The app treats object storage as a single bucket used for upload, download, presigned URLs, and delete operations.

Operationally, the backend and worker are not storage-agnostic today. They are S3-shaped in behavior, but MinIO-named in code, configuration, and local runtime.

## How Tightly Coupled Find Is To MinIO

Coupling is moderate to high.

### Code coupling

`backend/src/find_api/core/storage.py` is directly tied to the MinIO SDK:

- It imports `Minio` and `S3Error` directly.
- It constructs the client at import time from `settings.MINIO_*`.
- Public functions are thin wrappers around MinIO client methods.
- Logging and docstrings are MinIO-specific.

This is not yet a storage abstraction. It is a MinIO adapter exposed as application storage.

### Configuration coupling

`backend/src/find_api/core/config.py` exposes only MinIO-specific names:

- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- `MINIO_SECURE`
- `MINIO_PUBLIC_ENDPOINT`
- `MINIO_PUBLIC_READ`

This makes alternative S3-compatible backends possible only by reusing MinIO variable names.

### Runtime coupling

Both Compose files assume MinIO is the local storage runtime:

- Service name is `minio`.
- Default endpoint is `minio:9000`.
- The healthcheck calls the MinIO liveness path `/minio/health/live`.
- Port `9001` is exposed for the MinIO console.
- Volume names are MinIO-branded.
- Frontend environment variables are also MinIO-branded in Compose.

## MinIO-Specific Assumptions In The Current Design

The current code is S3-like, but it still embeds several MinIO-specific assumptions.

| Area | Current assumption | Why it matters |
| --- | --- | --- |
| SDK | Uses `minio` Python client directly | Swapping providers cleanly still requires code changes even if the provider is S3-compatible |
| Errors | Uses `S3Error` from the MinIO SDK | Error handling is tied to one client library |
| Naming | All backend settings are `MINIO_*` | Alternative providers inherit MinIO naming everywhere |
| Service discovery | Default backend endpoint is `minio:9000` in Compose | Local runtime assumes a specific container name |
| Healthcheck | Compose checks `/minio/health/live` | This does not generalize to RustFS, Garage, or SeaweedFS |
| Console | Compose exposes `9001` as a MinIO console port | This assumes a MinIO-style local admin UI layout |
| Bucket bootstrap | `init_storage()` auto-creates the bucket | Reasonable for local-first, but not all deployments want application-managed bucket creation |
| Bucket policy | `init_storage()` writes a JSON bucket policy | This depends on policy behavior being close enough to AWS S3/MinIO semantics |
| URL style | `get_file_url()` builds public URLs with bucket/path concatenation | Assumes path-style URL serving rather than provider-specific virtual-host or CDN patterns |
| Single-bucket model | One configured bucket for all objects | Fine for now, but it is a storage design choice that should belong in the abstraction |

## Comparison Of Candidate Directions

### Summary

| Option | S3 compatibility | Local Docker DX | OS fit for contributors | License | Migration complexity | Local-first fit |
| --- | --- | --- | --- | --- | --- | --- |
| MinIO transitional runtime + abstraction | High today, but public upstream is archived/read-only | Excellent in this repo already | Good via Docker Desktop on Windows/macOS/Linux | AGPLv3 source remains available, but community maintenance/support is no longer a healthy default assumption | Low | Strong as a short transition, weak as the final default |
| RustFS | Positioned as fully S3-compatible; docs recommend AWS SDKs and say MinIO SDKs work | Moderate; official Docker docs are more involved than MinIO and Linux-oriented | Best on Linux first; Docker can still help on Windows/macOS | Apache-2.0 | Low to moderate if abstraction exists | Strong |
| Garage | S3-compatible, aimed at small self-hosted geo-distributed deployments | Moderate; promising but less obviously one-command for this repo's current shape | Cross-platform through containers, but the cited project materials emphasize self-hosted cluster scenarios | AGPLv3 | Moderate | Strong |
| SeaweedFS | S3-compatible gateway/object store | Good; official quick start includes one command and Docker examples | Strongest cross-platform story in cited sources because official quick start includes `weed`/`weed.exe` and Docker | Apache-2.0 | Moderate | Strong |
| Provider-neutral S3 SDK approach | Depends on chosen backend; decouples Find from one vendor SDK | Best long-term because runtime can vary by Compose/profile | Good | Depends on runtime, not SDK | Moderate now, low later | Strong |

### Detailed Notes

#### 1. Keep MinIO only as a transitional runtime while adding an abstraction layer

Pros:

- Smallest code and Compose change from the current repo.
- Preserves the best current developer experience because both Compose files already work around a MinIO service.
- Keeps bucket bootstrap and presigned URL behavior close to current code.

Cons:

- Leaves the local default tied to a repository that was archived/read-only on April 25, 2026.
- Keeps AGPLv3 in the default storage runtime.
- Solves API coupling, but not the long-term maintenance concern around the default storage choice.

Assessment:

This is a good transition step, but a weak final state if the goal is to reduce strategic dependence on MinIO. New work should not deepen MinIO-specific coupling; it should make replacement easier.

#### 2. RustFS

Pros:

- Official docs position RustFS as S3-compatible and recommend using the official AWS S3 SDKs.
- Official docs also state MinIO SDKs can work by changing endpoint and credentials.
- Apache-2.0 is operationally simpler than AGPLv3 for many projects.
- Conceptually closest to a modern MinIO-style replacement.

Cons:

- The Docker installation docs reviewed here are more Linux-shaped than Find's current MinIO setup.
- Official Docker docs describe host config files and ownership requirements, which are heavier than Find's current one-service MinIO runtime.
- Compared with MinIO, the repo has less evidence in this review of a very mature "drop-in for every local dev workflow" experience.

Assessment:

RustFS is the strongest replacement candidate if Find wants a MinIO-like S3 backend under a permissive license, but it should follow a provider-neutral abstraction instead of another direct vendor SDK dependency.

#### 3. Garage

Pros:

- Official repo describes Garage as S3-compatible and designed for self-hosting at small to medium scale.
- It is explicitly positioned for resilient self-hosted deployments.
- It has been used in production by its authors since 2020, per the cited repo README.

Cons:

- Garage is optimized around a geo-distributed self-hosting story that is broader than Find's current single-node local dev needs.
- AGPLv3 does not improve the licensing story versus MinIO.
- Based on the materials reviewed here, Garage does not look like the most obvious "least-friction local replacement" for this repo.

Assessment:

Garage is technically plausible, but it does not materially simplify Find's near-term local-first developer workflow compared with the other options.

#### 4. SeaweedFS

Pros:

- Official repo positions SeaweedFS as S3-compatible.
- Official quick start supports a single command and Docker for local S3 use.
- The cited quick start explicitly mentions both `weed` and `weed.exe`, which is useful for Windows contributors.
- Apache-2.0 is permissive.

Cons:

- SeaweedFS is a broader storage platform, not only an S3 object server.
- Its architecture is richer than Find currently needs, which can mean more operational surface area than a MinIO-like replacement.
- The S3 API is one part of a larger system, so a simple integration can still carry more conceptual weight than the current model.

Assessment:

SeaweedFS has a strong local-dev story and good license posture, but it is probably more system than Find needs for the current scope.

#### 5. Provider-neutral S3-compatible SDK approach

Pros:

- Solves the real architectural problem in Find: vendor-specific coupling in application code.
- Lets Find keep a local-first default while treating MinIO, RustFS, Garage, SeaweedFS, or cloud S3 as runtime choices.
- Aligns with RustFS's own documentation, which recommends the official AWS S3 SDKs.

Cons:

- Requires a small refactor now instead of simply swapping a container image.
- Does not answer which local backend should become the long-term default.

Assessment:

This is the architectural move that should happen regardless of which S3-compatible runtime wins later.

## Developer Experience And Platform Fit

| Option | Docker/local developer experience | Windows/macOS/Linux notes |
| --- | --- | --- |
| MinIO | Best current fit for this repo because Compose already encodes the full workflow, but only as a transition while the archived upstream risk is handled | Good with Docker Desktop across platforms |
| RustFS | Viable, but the reviewed Docker docs are more involved and Linux-oriented | Likely workable via Docker Desktop, but the official install story reviewed here is less contributor-friendly on Windows/macOS |
| Garage | Viable, but current evidence points more toward self-hosted deployment than "frictionless local app dependency" | Likely container-friendly, but not the clearest cross-platform onboarding story in reviewed sources |
| SeaweedFS | Strong; official quick start is simple and Docker-backed | Best explicit multi-OS story in the reviewed sources |

## Migration Complexity Relative To Current Find

| Option | Code changes in `storage.py` | Config changes | Compose changes | Overall |
| --- | --- | --- | --- | --- |
| MinIO transitional runtime + abstraction | Moderate internal refactor, minimal behavior change | Rename or alias `MINIO_*` to neutral keys | Low | Lowest-risk transition, not the final target |
| RustFS | Same abstraction work, plus runtime validation | Neutral keys recommended | Replace storage service and healthcheck | Low to moderate |
| Garage | Same abstraction work, plus runtime validation | Neutral keys recommended | New service definition and likely different bootstrapping | Moderate |
| SeaweedFS | Same abstraction work, plus runtime validation | Neutral keys recommended | New service definition and endpoint semantics | Moderate |
| Stay as-is | None | None | None | Lowest effort, weakest long-term posture |

## Recommended Direction

Recommend:

1. Introduce a provider-neutral S3 storage abstraction in the backend.
2. Move Find off the MinIO SDK to a provider-neutral S3 client library.
3. Keep the runtime local-first and self-hostable.
4. Treat the local storage engine as a deployment choice, not an application dependency.
5. Evaluate RustFS first as the likely post-MinIO default once the abstraction exists.

### Why this path

This path separates two different decisions that are currently tangled together:

- application API choice
- local storage runtime choice

Right now Find hardcodes both. That makes any future provider evaluation more expensive than it needs to be.

The most realistic sequence is:

- first, remove MinIO-specific coupling from `storage.py` and `config.py`
- then, keep Compose storage-provider-specific at the service layer
- after that, compare RustFS, SeaweedFS, and a short-lived MinIO transition in a small runtime validation pass

That avoids a risky "rewrite and migrate at the same time" change.

## Recommended Minimal Refactor Shape For `storage.py`

This is intentionally structural only, not an implementation plan.

### Proposed interface shape

`storage.py` should expose a provider-neutral API such as:

- `init_storage()`
- `upload_file(file_data, object_name, content_type) -> str`
- `get_file(object_name) -> bytes`
- `get_file_url(object_name, expires=3600) -> str`
- `delete_file(object_name) -> None`

That public surface already exists. The change should be behind that surface.

### Proposed internal structure

- `StorageClient` protocol or small abstract base class
- `S3CompatibleStorageClient` implementation
- optional provider-specific bootstrap helpers only when needed

Example structure:

```text
backend/src/find_api/core/storage.py
backend/src/find_api/core/storage_backends/
  __init__.py
  base.py
  s3.py
```

### Responsibilities to separate

`storage.py` currently mixes:

- client construction
- bucket bootstrap
- policy bootstrap
- object CRUD
- URL generation

Those should be separated into:

- configuration loading
- client factory
- bootstrap/setup
- object operations
- URL generation strategy

### Configuration direction

Prefer neutral names such as:

- `STORAGE_BACKEND=s3`
- `STORAGE_ENDPOINT`
- `STORAGE_ACCESS_KEY`
- `STORAGE_SECRET_KEY`
- `STORAGE_BUCKET`
- `STORAGE_SECURE`
- `STORAGE_PUBLIC_ENDPOINT`
- `STORAGE_PUBLIC_READ`
- optional `STORAGE_AUTO_CREATE_BUCKET=true`

For compatibility, Find can temporarily support `MINIO_*` as aliases.

Alias timeline: introduce `STORAGE_BACKEND`, `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_BUCKET`, `STORAGE_SECURE`, `STORAGE_PUBLIC_ENDPOINT`, `STORAGE_PUBLIC_READ`, and `STORAGE_AUTO_CREATE_BUCKET` first, then support existing `MINIO_*` aliases for 2-3 releases or until RustFS validation completes, whichever comes first. Before removing the aliases, document a clear fallback: copy the existing `MINIO_*` values into the matching `STORAGE_*` keys and keep `STORAGE_BACKEND=s3`.

## Tradeoff Analysis For The Recommended Path

### Recommended path

Provider-neutral S3 abstraction now, RustFS as the first serious replacement candidate after abstraction, MinIO retained only as a transitional local runtime if needed.

### Benefits

- Removes the tightest form of coupling without forcing an immediate backend migration.
- Keeps Find local-first and self-hostable.
- Preserves current application behavior while making future runtime swaps cheaper.
- Improves the license posture if the project later chooses RustFS or SeaweedFS.

### Costs

- Small refactor cost in backend storage code and settings.
- Some temporary config compatibility work if both `MINIO_*` and `STORAGE_*` need to coexist.
- Need for a follow-up validation matrix against at least one alternative runtime.

### Why not recommend "replace MinIO immediately"

- The current backend code is not abstracted enough to make that a clean first change.
- A direct swap now would couple Find to a new provider without solving the underlying design problem.
- The issue explicitly asks for research and a concrete recommendation, not a migration.

## Decision

Choose a provider-neutral S3 abstraction as the next architectural step.

Use that abstraction to decouple Find from the MinIO SDK first.

After the abstraction lands, validate RustFS as the leading replacement candidate for the default local object-store runtime. Keep SeaweedFS as a viable fallback if the project later prioritizes cross-platform local developer ergonomics over "closest MinIO-like replacement." Do not move to Garage unless Find develops stronger requirements around geo-distributed self-hosting.

## References

- Current repository files reviewed in this ADR:
  - `backend/src/find_api/core/storage.py`
  - `backend/src/find_api/core/config.py`
  - `docker-compose.yml`
  - `docker-compose.light.yml`
- MinIO GitHub repository archive notice: https://github.com/minio/minio
- RustFS SDK overview: https://docs.rustfs.com/developer/sdk/
- RustFS Docker installation docs: https://docs.rustfs.com/installation/docker/index.html
- RustFS GitHub repository: https://github.com/rustfs/rustfs
- Garage GitHub repository: https://github.com/deuxfleurs-org/garage
- SeaweedFS GitHub repository: https://github.com/seaweedfs/seaweedfs
