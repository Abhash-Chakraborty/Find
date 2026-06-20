# Reprocess / Retry Analysis Feature

**Status:** Complete  
**Last reviewed:** 2026-05-28  
**Completion evidence:** Backend endpoint, frontend actions, and focused backend/frontend tests are present in the current codebase.

This document describes the "reprocess" (retry analysis) feature added to the project, what was changed, how the tests were written, and how to run them locally.

## Summary

- Adds a backend endpoint to re-enqueue the existing `analyze_image` worker for an existing media row without requiring a duplicate upload.
- Adds a frontend action (modal and gallery card) to trigger the reprocess for eligible media rows.
- Adds unit tests for both backend and frontend and developer documentation for running the tests.

## What changed (high level)

- Backend
  - `backend/src/find_api/routers/gallery.py`: adds `POST /api/image/{media_id}/reprocess` endpoint that:
    - validates eligibility (failed or indexed with missing caption),
    - resets `status` to `pending`, clears stale `error_message`/`processed_at`, and
    - enqueues the existing `find_api.workers.jobs.analyze_image(media_id)` job via the configured RQ queue.

- Frontend
  - `frontend/src/lib/api.ts`: adds `reprocessImage(mediaId) -> ReprocessResponse` wrapper.
  - `frontend/src/components/image-preview-modal.tsx`: adds a "Retry Analysis" action visible for `failed` images (and indexed images missing caption).
  - `frontend/src/app/gallery/page.tsx`: shows a per-card retry icon for `failed` images.

- Tests
  - Backend tests: `backend/tests/test_reprocess.py` (plus test shims in `backend/tests/conftest.py`) — uses an in-memory SQLite DB (StaticPool) and test-time shims for RQ/MinIO to keep tests fast and isolated.
  - Frontend tests: `frontend/src/__tests__/reprocess.test.ts` — Vitest unit tests for the API wrapper and UI eligibility logic. Tests mock `axios` and use a small helper to provide a fake `api` axios instance.

## How the tests were written

- Backend
  - Tests exercise the FastAPI router directly using `TestClient`.
  - Heavy external dependencies (MinIO, RQ, pgvector) are stubbed in `conftest.py` so the test suite does not require those services.
  - The DB is created in-memory with SQLAlchemy `StaticPool` so the app and tests share the same memory DB.

- Frontend
  - Tests use Vitest and @testing-library patterns. The `axios` module is mocked and `axios.create()` is made to return a small object implementing `post/get/delete` so the exported `api` instance can be spied on.

## How to run the tests locally

Backend (Windows PowerShell):

```powershell
Set-Location d:\gssoc\find\Find\backend
$env:PYTHONPATH = 'src'; py -m pytest tests/test_reprocess.py -q
```

Backend (Linux/macOS / POSIX):

```bash
cd backend
PYTHONPATH=src pytest tests/test_reprocess.py -q
```

Frontend (PowerShell):

```powershell
Set-Location d:\gssoc\find\Find\frontend
npm install    # or pnpm install
npx vitest run src/__tests__/reprocess.test.ts
```

Frontend (POSIX):

```bash
cd frontend
pnpm install    # or npm install
pnpm vitest run src/__tests__/reprocess.test.ts
```

## Notes

- The backend tests were designed to be fast and not require a running worker or object storage instance. If you run full integration tests (manual run), you will need MinIO and an RQ worker configured.
- The frontend tests cover the small UI/logic changes; integration/e2e tests are not included in this change.


