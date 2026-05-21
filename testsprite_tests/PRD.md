# Find Product Requirements For TestSprite

## Product Summary

Find is a local-first AI image intelligence app. Users upload images, the
backend analyzes them locally, and the frontend lets users browse, search,
cluster, and manage their visual library.

The default product expectation is that images and metadata stay on the user's
machine. The app should work in a Docker-based local setup without requiring a
hosted cloud service.

## Core Users

- Local users managing their own image library.
- Small trusted groups, friends, or family sharing one local Find instance.
- Contributors validating that basic product flows still work after a PR.

## Core Pages

### Upload

Users can upload individual image files or a ZIP archive of images. The UI must
show the selected upload mode, reject invalid file types, and surface useful
errors from the backend.

Expected behavior:

- The upload page loads without authentication.
- File mode is available by default.
- ZIP mode is visible and selectable.
- Invalid uploads fail with a clear error.
- Recent uploads show processing status when jobs are queued.

### Gallery

Users can browse uploaded media, filter by analysis status, open image previews,
like images, download images, retry failed analysis, and delete images.

Expected behavior:

- The gallery page loads even when no images exist.
- The gallery API returns a stable paginated shape.
- Status filters support only pending, processing, indexed, and failed.
- Invalid status filters are rejected by the API.
- Empty states should match the selected filter.

### Search

Users can search by natural-language memory of an image. Search should return a
stable results page and should not break when no indexed images exist.

Expected behavior:

- The search page loads.
- Suggested query chips are visible.
- Search requests should fail gracefully if the backend cannot search yet.

### Clusters

Users can view image clusters created from local image embeddings and trigger a
manual recluster job when there are enough indexed images.

Expected behavior:

- The clusters page loads.
- Empty cluster states are clear.
- Manual clustering should not crash when there are too few images.

### People

Users can view person-based clusters when face clustering is enabled. This is an
advanced local-only feature and must not be required for basic smoke tests.

Expected behavior:

- If present, the people page should load without breaking navigation.
- Missing face data should show an empty state, not an error.

## API Requirements

### Health

`GET /health` should return HTTP 200 with a healthy status when the API is
ready.

### Gallery

`GET /api/gallery` should return:

- `items`: list
- `total`: number
- `page`: number
- `limit`: number

`GET /api/gallery?status=not-a-real-status` should return a validation error.

### Bulk Upload

`POST /api/upload/bulk` should reject non-ZIP uploads with a user-safe error.

## Non-Goals For General PR Smoke Tests

- Do not require real ML model downloads.
- Do not require GPU acceleration.
- Do not require third-party cloud credentials.
- Do not require a large seeded image library.
- Do not test private user data or secrets.

## TestSprite General Test Scope

For every non-draft PR, TestSprite should run a small stable smoke suite:

- API health check.
- Gallery API shape check.
- Gallery invalid status validation.
- Bulk upload invalid ZIP validation.
- Frontend load checks for upload, gallery, search, and clusters.
- Basic upload UI visibility check, including ZIP mode.

These tests are intentionally broad and PR-agnostic. Feature-specific tests can
be added later, but the general suite should remain stable across documentation,
frontend, backend, and CI-only PRs.
