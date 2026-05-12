# Contributing to Find

Thanks for contributing to Find.

This project is part of **GSSoC'26**, and we want contributions to be beginner-friendly, reviewable, and production-safe.

## Before you start

1. Check open issues and comment on one before starting work.
2. Wait for maintainer confirmation/assignment.
3. Fork the repository and branch from `main`.

## Local setup

### Prerequisites

- Node.js 18+ and `pnpm`
- Python 3.12 and `uv`
- Docker and Docker Compose (recommended path)
- PostgreSQL + `pgvector`, Redis, and MinIO (for non-Docker local runs)

### Run with Docker (recommended)

```bash
docker compose up --build
```

### Run manually

Backend:

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
```

## Pull request format

Each PR must:

1. Link an issue (`Fixes #<issue-number>`).
2. Explain what changed and why.
3. Include manual test steps and expected result.
4. Add screenshots/videos for UI changes.
5. Keep scope focused to one issue.

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

## Community standards

- Be respectful and constructive.
- Follow the [Code of Conduct](./CODE_OF_CONDUCT.md).
- Use GitHub Issues/PR comments as the official project communication channel.

## License

By contributing, you agree your contributions are licensed under the [MIT License](./LICENSE).
