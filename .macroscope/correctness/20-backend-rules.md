Apply these rules when reviewing changes under `backend/**`, `docker-compose*.yml`, or storage / queue code.

Backend review priorities:
- Do not expose raw exception text, stack traces, secrets, or filesystem details to API clients.
- Preserve the local-first architecture. Storage, worker, ML, and queue changes must stay local by default.
- Watch for status transition bugs around `pending`, `processing`, `indexed`, `failed`, and any retry or reconciliation path.
- Verify upload validation, archive safety, thumbnail generation, and storage writes remain safe and bounded.
- Flag dependency or Docker changes that increase risk, break GPU/full-mode behavior, or silently weaken security.
- Require focused tests for behavior changes in routers, workers, storage, or model-loading flows.
