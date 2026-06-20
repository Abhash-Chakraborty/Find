# GitHub Copilot Instructions

Follow the repository guidance in [AGENTS.md](../AGENTS.md) and the security policy in [docs/policies/agent-security.md](../docs/policies/agent-security.md).

Important Find-specific rules:

- Keep Find local-first. Do not add cloud uploads, telemetry, hosted model APIs, or analytics unless the linked issue explicitly asks for that architecture.
- Do not commit secrets, `.env`, database files, MinIO data, Docker volumes, model weights, or generated caches.
- Keep frontend API types and helpers in `frontend/src/lib/api.ts` when changing contracts.
- Keep FastAPI routers thin and place storage, queue, database, and ML logic in existing backend modules.
- Preserve user data for destructive actions. Do not clear clusters, media, feedback, thumbnails, or storage unless a verified replacement path exists.
- Keep PRs scoped to the linked issue and avoid unrelated formatting churn.
