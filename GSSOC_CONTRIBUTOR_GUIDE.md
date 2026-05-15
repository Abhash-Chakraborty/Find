# GSSoC'26 Contributor Guide

This guide is the fastest path for GSSoC'26 contributors to understand Find, set up the project, choose the right development mode, and open a reviewable pull request.

## Start here

Read these files in this order:

1. [README.md](./README.md) - project overview, architecture, run commands, endpoints, and troubleshooting.
2. [CONTRIBUTING.md](./CONTRIBUTING.md) - contribution rules, PR expectations, checks, and review process.
3. [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) - community standards and reporting process.
4. [.github/pull_request_template.md](./.github/pull_request_template.md) - what your PR description must include.
5. [AGENTS.md](./AGENTS.md) - repository structure, coding style, verification commands, and security notes.

## What Find does

Find is a local-first AI image intelligence app. Users upload images, the backend stores them locally, a worker extracts image metadata and embeddings, and the frontend lets users browse, search, like, delete, and cluster indexed images.

Main stack:

- Frontend: Next.js 16, React 19, React Query, Tailwind CSS, Biome.
- Backend: FastAPI, SQLAlchemy, PostgreSQL + pgvector, Redis, RQ, MinIO.
- Full ML pipeline: YOLOv10, Florence-2, PaddleOCR, SigLIP through `open-clip`, HDBSCAN.

Important paths:

- `frontend/src/app/` - Next.js pages and UI.
- `frontend/src/lib/` - frontend API client and shared helpers.
- `backend/src/find_api/` - FastAPI app, routers, models, storage, queue, worker, and ML wrappers.
- `docker-compose.yml` - full GPU-oriented stack.
- `docker-compose.light.yml` - lightweight contributor stack.
- `.env.example` - documented local environment values.

## Contribution workflow

1. Find an issue labeled `good first issue`, `help wanted`, `gssoc26`, `level 1`, `level 2`, or `level 3`.
2. Comment on the issue and wait for maintainer assignment before starting.
3. Fork the repository and create a branch from `main`.
4. Keep the change scoped to one issue.
5. Run the relevant checks before opening a PR.
6. Open a PR against `main` and fill out the full PR template.

Do not open broad PRs that mix unrelated UI, backend, docs, and formatting changes. Small, focused PRs are faster to review.

## Recommended setup: light contributor mode

Most GSSoC work should start with the light stack. It avoids the 30-40 GB first-run cost from model downloads and GPU-oriented dependencies while still exercising the real app flow.

From the repository root:

```bash
docker compose -f docker-compose.light.yml up --build
```

What light mode gives you:

- PostgreSQL + pgvector, Redis, MinIO, FastAPI, worker, and web services.
- Upload, job status polling, gallery, search, and clustering paths.
- `ML_MODE=mock`, deterministic mock metadata, and schema-compatible vectors.
- No CUDA image, GPU requirement, model cache mount, Florence-2, SigLIP, PaddleOCR, YOLO, or CUDA PyTorch downloads.

Use light mode for:

- Frontend UI changes.
- API and routing changes that do not require real ML quality.
- Upload/gallery/search/clustering workflow changes.
- Documentation, CI, contributor-experience, and tooling changes.

## Full setup: real ML inference

Use the full stack only when your issue needs real model behavior, real captions, real object detection, real OCR, or ML performance validation.

```bash
docker compose up --build
```

Notes:

- The full Docker stack expects NVIDIA GPU support by default.
- First run downloads large models and dependencies.
- Cached models live in the Docker `model_cache` volume.

## Manual local setup

Use this only if you are not using Docker.

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Backend API:

```bash
cd backend
uv sync --group dev
uv run uvicorn find_api.main:app --reload
```

Worker:

```bash
cd backend
uv run rq worker --url redis://localhost:6379 high default low
```

Real local ML dependencies:

```bash
cd backend
uv sync --group dev --extra ml
```

Manual local setup also requires PostgreSQL with `pgvector`, Redis, and MinIO.

## Useful URLs

When the stack is running:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

## Quality checks

Frontend:

```bash
cd frontend
pnpm check
pnpm build
```

Backend:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
```

Compose validation:

```bash
docker compose config
docker compose -f docker-compose.light.yml config
```

## Manual testing checklist

Use this checklist when your change touches app behavior:

- Upload one image from `/upload`.
- Upload a small ZIP from `/upload`.
- Confirm job status polling completes.
- Confirm images appear in `/gallery`.
- Open an image detail modal and check metadata.
- Run a search from `/search`.
- Open `/clusters` and trigger clustering when relevant.
- Verify delete, like, and download actions if you touched gallery behavior.

In light mode, metadata and search results are mock-backed. Use the full stack before claiming real ML quality improvements.

## PR requirements

Before opening a pull request:

- Link the assigned issue using `Fixes #<issue-number>`.
- Explain what changed and why.
- Include exact test commands and manual test steps.
- Add screenshots or recordings for UI changes.
- Keep the PR scoped to one issue.
- Make sure CI-relevant checks pass locally.
- Do not commit `.env`, secrets, database files, MinIO data, model weights, `node_modules`, `.next`, caches, or generated Python bytecode.

## Commit messages

Use concise conventional prefixes:

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `chore:`
- `test:`
- `ci:`

Example:

```text
docs: add GSSoC contributor quick start
```

## Getting help

Use GitHub issues and PR comments for project communication. For sensitive Code of Conduct reports, follow [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).
