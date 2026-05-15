# Repository Guidelines

## Project Structure & Module Organization

Find is a local-first AI image intelligence app. Key paths:

- `backend/src/find_api/` - FastAPI API, SQLAlchemy models, Redis/RQ jobs, MinIO helpers, and ML wrappers.
- `frontend/src/app/` - Next.js App Router UI.
- `frontend/src/lib/` - React Query API client, media URL helpers, and shared utilities.
- `docker-compose.yml` - PostgreSQL/pgvector, Redis, MinIO, API, worker, and web orchestration.
- `.env.example` - documented local configuration. Keep real `.env` files private.
- `.github/workflows/ci.yml` - frontend and backend CI checks.

There is no committed test directory yet. Avoid generated paths such as `frontend/.next/`, `frontend/node_modules/`, `.ruff_cache/`, `__pycache__/`, and model weights.

## Build, Test, and Development Commands

From the repository root:

```bash
docker compose up --build
```

Starts the full local stack. The default backend/worker expects NVIDIA GPU support.

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
pnpm check
pnpm build
```

`pnpm dev` runs Next.js, `pnpm check` runs Biome, and `pnpm build` verifies production output.

Backend:

```bash
cd backend
uv sync
uv run uvicorn find_api.main:app --reload
uv run rq worker --url redis://localhost:6379 high default low
uv run ruff check .
uv run ruff format --check .
```

Run the API and worker separately when not using Docker.

## Coding Style & Naming Conventions

Frontend code uses TypeScript strict mode, 2-space indentation, double quotes, and Biome formatting. Keep shared API types and functions in `frontend/src/lib/api.ts`.

Backend code targets Python 3.12 and is checked with Ruff. Use `snake_case` for Python functions/modules and `PascalCase` for SQLAlchemy model classes. Keep routers thin; put storage, queue, database, and ML logic in their existing modules.

## Testing Guidelines

No formal test suite is committed. Run the closest checks: `pnpm check && pnpm build` for frontend work and `uv run ruff check . && uv run ruff format --check .` for backend work. For integration changes, manually verify upload, job status polling, gallery, search, and clustering.

## Commit & Pull Request Guidelines

Recent commits use concise prefixes such as `feat:`, `docs:`, `refactor:`, `update:`, and `Fix CI:`. Follow that style with an imperative summary.

Pull requests should include a clear description, linked issue when relevant, testing notes, screenshots or recordings for UI changes, and documentation updates for API, environment, or workflow changes.

## Security & Configuration Tips

Do not commit `.env`, MinIO data, database files, downloaded model weights, or secrets. Keep `EMBEDDING_DIM` aligned with the configured CLIP/SigLIP model and pgvector columns.
