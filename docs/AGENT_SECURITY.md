# AI Agent Security Policy

Find is a local-first AI image intelligence app. Agents must preserve that privacy model unless a linked issue explicitly asks for a different architecture.

## Sensitive Data

Treat these as private user data:

- uploaded images, thumbnails, and object-storage files
- captions, OCR text, EXIF metadata, detected objects, embeddings, and vectors
- face/person data, people names, clusters, and personalization feedback
- database dumps, backup files, logs, and generated exports
- `.env` values, access keys, API keys, signed URLs, tokens, and local absolute paths

## Non-Negotiable Rules

- Do not commit `.env`, database files, MinIO/RustFS data, Docker volumes, model weights, or generated caches.
- Do not hardcode credentials, public buckets, signed URLs, API keys, or maintainer-local paths.
- Do not add telemetry, analytics, hosted model APIs, remote logging, or cloud upload paths unless the linked issue explicitly requires it.
- Do not send images, embeddings, captions, OCR text, face data, or feedback to external services by default.
- Do not weaken upload validation, ZIP/archive safety checks, dependency policy, secret scanning, or CI gates to make a PR pass.
- Do not print secrets, signed URLs, tokens, raw environment values, or private file paths in logs or user-facing errors.
- Use existing sanitized error helpers for backend user-facing errors.

## Local-First ML And Privacy

- Keep captioning, OCR, object detection, embeddings, face detection, clustering, and feedback processing local by default.
- Hidden/vault work must assume raw image files are sensitive and must not rely on UI hiding alone.
- Face/person and feedback features must avoid cloud sync or cross-user training unless explicitly designed and approved.
- Model personalization must be opt-in, local-only, resettable, and explainable.

## Storage And Database Safety

- Preserve uploaded media, thumbnails, metadata, feedback, and clusters unless the operation intentionally changes them.
- For destructive flows such as delete, reprocess, recluster, migration, cache cleanup, or vault encryption, verify the replacement or rollback path before removing existing data.
- Keep object storage and metadata database behavior aligned. Do not introduce orphaned files or dangling database rows.
- Never make buckets public by default.

## Dependency And CI Safety

- Prefer existing libraries and patterns before adding dependencies.
- Add dependencies only when the issue justifies the cost and the package is actively maintained.
- Keep dependency changes scoped and explain security or size tradeoffs.
- Do not bypass failing tests without explaining the root cause.
- Do not mark PRs ready if security checks, linked-issue checks, or relevant CI checks are failing.

## Agent Output Rules

- Keep PRs focused on the assigned issue.
- Do not include unrelated refactors, formatting churn, generated files, or personal tooling files.
- Document any skipped test or manual verification honestly.
- When unsure about security impact, leave a note for the maintainer instead of guessing.
