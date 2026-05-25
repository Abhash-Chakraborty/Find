# Contributing to Find

Thanks for contributing to Find.

This project is part of **GSSoC'26**, and we want contributions to be beginner-friendly, reviewable, and production-safe.

For repo-aware coding-agent and contributor guidance, start with [AGENTS.md](./AGENTS.md).

## Before you start

1. Check open issues and comment on one before starting work.
2. Wait for maintainer confirmation/assignment.
3. Fork the repository and branch from `main`.

## Repository protection rules

- Direct pushes to `main` are blocked.
- Open a pull request from your branch.
- PR merge requires:
  - Passing CI checks
  - At least one approval
  - Resolved review conversations

## Local setup

### Prerequisites

- Node.js 18+ and `pnpm`
- Python 3.12 and `uv`
- Docker and Docker Compose (recommended path)
- PostgreSQL + `pgvector`, Redis, and MinIO (for non-Docker local runs)

### Run with Docker (recommended)

For most UI, API, docs, and workflow contributions, start with the light stack:

```bash
docker compose -f docker-compose.light.yml up --build
```

This uses `ML_MODE=mock`, skips GPU access, and avoids downloading Florence-2, SigLIP, PaddleOCR, YOLO, and CUDA PyTorch assets. Upload, worker processing, gallery, search, and clustering still run end-to-end with deterministic mock metadata and vectors.

Use the full stack only when your change needs real ML inference:

```bash
docker compose up --build
```

## Mock mode vs full ML mode

The light stack (`docker-compose.light.yml`) runs with `ML_MODE=mock`. The worker
records real image dimensions and EXIF data but replaces all model outputs with
deterministic stubs:

- **Captions** — a fixed placeholder string, not a real image description.
- **Object detection** — an empty list or static stub, not real YOLO output.
- **OCR** — an empty string, not real PaddleOCR output.
- **Embedding vectors** — zero-filled or seeded values of the correct shape, with no
  semantic meaning. Search results will appear but their ranking is arbitrary.

### When the light stack is enough

Use `docker-compose.light.yml` (mock mode) when your change involves:

- Any frontend code (UI, layout, styling, components)
- API routing, request/response shapes, validation, or error handling
- Upload, job-status polling, gallery, like, delete, or clustering workflow
- Documentation, CI configuration, or contributor tooling

The full data pipeline — MinIO, PostgreSQL, Redis, RQ, and the worker — still runs
end-to-end in mock mode. You can verify that data flows correctly through the system
without any model downloads or GPU requirements.

### When the full stack is required

Use `docker compose up --build` (full ML mode) when your change or bug report involves:

- Caption content or quality
- Search relevance (whether the right images rank for a query)
- Object detection output
- OCR accuracy
- Clustering quality or grouping logic
- Any change to ML model parameters or the inference pipeline

> ⚠️ **Do not file ML quality bugs based on mock-mode observations.** Mock output is
> intentionally fake. Any caption or search behavior you observe in mock mode is not
> representative of real model output and will not reproduce in full mode. Confirm all
> ML quality claims in the full stack before opening an issue.


### Run manually

Backend:

```bash
cd backend
uv sync --group dev
uv run uvicorn find_api.main:app --reload
```

Use `uv sync --group dev --extra ml` only when you need real local ML inference outside Docker.

Worker:

```bash
cd backend
uv run rq worker --url redis://localhost:6379 high default low
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

## Commit message convention

Use short conventional prefixes:

- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `chore:`
- `test:`
- `ci:`

Example:

```text
feat: add upload validation for large ZIP files
```

## Code style and quality checks

Run these before opening a PR.

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
uv run pytest tests/ -v
```

## Pull request format

Each PR must:

1. Link an issue (`Fixes #<issue-number>`).
2. Explain what changed and why.
3. Include manual test steps and expected result.
4. Add screenshots/videos for UI changes.
5. Keep scope focused to one issue.
6. Target the `main` branch.
7. Pass CI checks (`frontend-check`, `backend-check`).

Use the PR template in `.github/pull_request_template.md`.

## Review expectations

- Maintainers usually respond within **24-48 hours**.
- PRs without issue linkage, test notes, or clear scope can be sent back for updates.
- Do not mark conversations as resolved unless feedback is addressed.
- Do not force push over unresolved review comments without explanation.

## Issue quality expectations

If you open a new issue, include:

- Problem statement
- Reproduction steps (for bugs)
- Expected vs actual behavior
- Screenshots/logs where relevant
- Suggested approach (optional but helpful)

Useful labels:

- `good first issue`: beginner-friendly tasks
- `help wanted`: priority items where maintainer help is needed
- `gssoc26`: scoped for GSSoC'26
- `level:beginner`, `level:intermediate`, `level:advanced`, `level:critical`: expected complexity

## Community standards

- Be respectful and constructive.
- Follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
- Use GitHub Issues/PR comments as the official project communication channel.

## License

By contributing, you agree your contributions are licensed under the [MIT License](./LICENSE).
