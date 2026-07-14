# Privacy-Safe Local Diagnostics Bundle

Local-only support export for Find. Generate this bundle on your machine, review
it, then attach the JSON to a GitHub issue when asking for help. **Nothing is
uploaded automatically** — there is no telemetry, no cloud exporter, and no
outbound webhook.

## How to generate

### Admin API (explicit request)

```http
GET /api/admin/diagnostics/bundle
Authorization: Bearer <admin-session-token>
```

- **Shared mode:** admin authentication required (`403` for non-admins, `401` if unauthenticated).
- **Local / single-user mode:** open (same pattern as other admin endpoints).
- Response is JSON with `Content-Disposition: attachment; filename="find-diagnostics-bundle.json"`.
- Header `X-Find-Diagnostics: local-only` marks the payload as a local export.

Example with the running API:

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/admin/diagnostics/bundle \
  -o find-diagnostics-bundle.json
```

Open the file and search for any unexpected personal data before attaching it to
an issue.

## What is included

| Section | Contents |
| --- | --- |
| `schema_version` / `generated_at` | Bundle format version and UTC timestamp |
| `privacy_notice` | Short reminder that the export is local-only |
| `app` | App version, `ENVIRONMENT` |
| `runtime` | Python version/implementation, OS name/release/machine |
| `migrations` | Alembic current revision, heads, status (`ok` / `behind` / …) |
| `services` | Connectivity + latency for PostgreSQL, Redis, and storage (MinIO or local). Errors are sanitized. |
| `queue` | Queue mode, depth / queued / started / failed (/ finished when available) |
| `models` | `ML_MODE`, accel mode, configured model **names**, embedding dim, whether remote ML is configured (**boolean only**), currently loaded model names |
| `errors` | Up to 20 recent sanitized ERROR log lines plus failed media analysis messages. Credentials and secret assignments are stripped; **hostnames and residual path fragments may still appear** after sanitization. |

Service checks only report `ok`, `latency_ms`, optional sanitized `error`, and for storage the backend kind (`minio` / `local`). Connection credentials are never included. Sanitized error strings may still contain hostnames or path fragments — only URL credentials (user/password) are stripped from URLs.

## What is excluded

The redaction layer is **allowlist-first**: unknown keys are denied. Explicitly stripped categories include:

- Passwords, tokens, API keys, access/secret keys, bearer credentials, session cookies
- Database / Redis / MinIO connection strings and storage keys (`minio_key`, `thumbnail_key`)
- Absolute file paths and media filenames
- Captions, OCR text, EXIF / metadata JSON blobs
- Embeddings / vectors
- Face and person identifiers / landmarks
- User identifiers (user id, uploader, email, username, display name)
- Remote ML URL and API key values (only a boolean `remote_ml_configured` is kept)
- Raw image bytes or thumbnails (never collected)

String values under allowlisted keys are still scrubbed with path, filename, URL-credential, and token patterns.

## Privacy guarantees

1. **Explicit action only** — a human (or admin client) must call the endpoint.
2. **Local response** — the API returns JSON to the requester; the server does not POST the bundle anywhere.
3. **Redaction before return** — `collect_diagnostics_bundle()` always runs `redact_payload()`.
4. **Credential stripping, not absolute silence** — passwords/tokens/storage keys/captions/OCR/embeddings/faces/user ids are removed. Hostnames and path-like fragments **may** still appear in sanitized error messages; review the JSON before attaching it to an issue.
5. **Suitable for GitHub issues** — after a manual review, attach `find-diagnostics-bundle.json` to help maintainers reproduce environment/migration/queue problems without receiving private media content.

## Related

- Issue tracking: [#347](https://github.com/Abhash-Chakraborty/Find/issues/347)
- Agent security policy: [policies/agent-security.md](./policies/agent-security.md)
- Setup troubleshooting: [guides/common-setup-errors.md](./guides/common-setup-errors.md)
