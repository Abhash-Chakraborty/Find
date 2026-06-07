# Repository Guidelines For Agents

This is the main shared instruction file for AI coding agents working on Find. Tool-specific files should stay short and point back here so the rules do not drift.

## Agent Compatibility And Placement

- `AGENTS.md` is the main shared source for Codex, opencode, Cursor, Windsurf, Copilot-style agents, and other tools that support this convention.
- `CODEX.md` is a Codex compatibility pointer back to this file.
- `CLAUDE.md` is a Claude Code entry point and imports this file.
- `.github/copilot-instructions.md` is the GitHub Copilot repository instruction entry point and points back here.
- `.cursor/rules/find-agent-guidelines.mdc` is a symlink back to this file for Cursor.
- `.windsurfrules` is the Windsurf entry point and points back here.
- `.agents.md` is a lowercase compatibility pointer for tools or contributors that look for that spelling.
- `docs/policies/agent-security.md` contains the detailed AI-agent security policy for this project.
- Keep tool-specific files as thin pointers. Put shared behavior, project structure, commands, and review expectations in this file.
- If a tool supports extra local or user-level rules, keep those personal files outside the repo. Do not commit personal agent memories or machine-specific rules.
- If future scoped rules are needed, prefer additional `AGENTS.md` files inside a specific directory only when the guidance truly applies only to that directory.

## Start Here

1. Read `README.md` for product scope, architecture, and run modes.
2. Read `CONTRIBUTING.md` for branch, PR, and review process.
3. Check the linked issue before editing. If the PR has no linked issue, keep the change blocked until the maintainer confirms scope.
4. Keep the branch focused on one issue. Do not bundle opportunistic refactors, unrelated docs, formatting churn, or cleanup.
5. Read `docs/policies/agent-security.md` before touching upload, storage, ML, face/person data, feedback, secrets, Docker, CI, or dependency files.

## Project Structure & Module Organization

Find is a local-first AI image intelligence app. Key paths:

- `backend/src/find_api/` - FastAPI API, SQLAlchemy models, Redis/RQ jobs, MinIO helpers, and ML wrappers.
- `frontend/src/app/` - Next.js App Router UI.
- `frontend/src/lib/` - React Query API client, media URL helpers, and shared utilities.
- `docker-compose.yml` - PostgreSQL/pgvector, Redis, MinIO, API, worker, and web orchestration.
- `.env.example` - documented local configuration. Keep real `.env` files private.
- `.github/workflows/ci.yml` - frontend and backend CI checks.

Avoid generated paths such as `frontend/.next/`, `frontend/node_modules/`, `.ruff_cache/`, `__pycache__/`, and model weights.

Understand the user-visible flow before editing behavior: upload, worker processing, status polling, gallery, search, clustering, people, preview modal, and feedback.

## Build, Test, and Development Commands

From the repository root:

```bash
docker compose up --build
```

Starts the full local stack. The default full-stack ML workflow is optimized for NVIDIA GPU support.

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
uv run pytest tests/ -v
```

Run the API and worker separately when not using Docker.

Prefer the light stack for routine UI, API, docs, and workflow work:

```bash
docker compose -f docker-compose.light.yml up --build
```

Use the full stack only when the change needs real ML behavior.

## Coding Style & Naming Conventions

Frontend code uses TypeScript strict mode, 2-space indentation, double quotes, and Biome formatting. Keep shared API types and functions in `frontend/src/lib/api.ts`.

Backend code targets Python 3.12 and is checked with Ruff. Use `snake_case` for Python functions/modules and `PascalCase` for SQLAlchemy model classes. Keep routers thin; put storage, queue, database, and ML logic in their existing modules.

For cross-stack changes, verify the API contract in `frontend/src/lib/api.ts` and the matching FastAPI router before changing either side.

## Testing Guidelines

Run the automated test suite before opening a PR: `pnpm check && pnpm build` for frontend work and `uv run ruff check . && uv run ruff format --check . && uv run pytest tests/` for backend work. For integration changes, manually verify upload, job status polling, gallery, search, and clustering.

## Commit & Pull Request Guidelines

Recent commits use concise prefixes such as `feat:`, `docs:`, `refactor:`, `update:`, and `Fix CI:`. Follow that style with an imperative summary.

Pull requests should include a clear description, linked issue when relevant, testing notes, screenshots or recordings for UI changes, and documentation updates for API, environment, or workflow changes.

## Security & Configuration Tips

Do not commit `.env`, MinIO data, database files, downloaded model weights, or secrets. Keep `EMBEDDING_DIM` aligned with the configured CLIP/SigLIP model and pgvector columns.

Follow the detailed agent security policy in `docs/policies/agent-security.md`. In short: Find is local-first and privacy-focused. Do not add cloud calls, hosted model APIs, telemetry, analytics, or external uploads for user images, captions, OCR text, embeddings, faces, feedback, or storage data unless the linked issue explicitly asks for that architecture.

## Agent Review Checklist

Before finishing a change, verify:

- The diff matches the assigned issue and does not touch unrelated files.
- Generated files, caches, model weights, Docker volumes, and local databases are not included.
- Frontend text is visible in both dark and light mode when UI is touched.
- Backend changes include focused tests when they affect API behavior, storage, queues, models, or migrations.
- Docs changes describe the current project accurately and do not invent commands or architecture.
- PR notes say what was tested and what was not tested.
