# Image Loading Behavior

This guide describes how Find should load thumbnails and full-resolution originals
across the UI.

## Overview

Find serves images in two distinct modes depending on context:

- **Thumbnails**: small optimized variants used everywhere images appear in a grid
  or list.
- **Full-resolution originals**: the unmodified source file, used for detailed
  preview and download actions.

This distinction matters for performance. Loading full-size images across an
entire gallery or search results page puts unnecessary pressure on object
storage, network bandwidth, and the browser's rendering pipeline. Grid views
should prefer thumbnails without sacrificing original quality for inspection or
download.

## Where Each Image Size Is Used

### Thumbnail views (small images)

The following views should display thumbnail-sized images rather than originals:

- **Gallery** (`GET /api/gallery`) - the main image grid on the home/gallery page.
- **Search results** (`GET /api/search?q=...`) - the grid of results returned
  for a natural-language query.
- **Clusters page** (`GET /api/clusters`) - the cluster overview grid showing
  representative images per cluster.
- **Cluster detail** (`GET /api/cluster/{cluster_id}`) - the member image grid
  inside a single cluster.
- **People page** (`GET /api/people`, `GET /api/people/{person_id}/images`) -
  person-grouped views that display small face or image thumbnails.

In all these views, the goal is to render many images simultaneously without fetching large files.

### Full-resolution views

- **Preview modal** - when a user clicks an image to inspect it in detail, the
  modal can use the original URL from the image detail response.
- **Download** - the file served for download should always be the original,
  uncompressed source.

## Quality Preservation

Thumbnail generation must not alter or degrade the original image stored in the
configured object store. The original file is the source of truth and should
remain untouched. Thumbnails are derived copies produced separately and sized for
grid/list display.

This means:

- The original uploaded file is stored as-is in object storage.
- Thumbnails are generated from the original without modifying or replacing it.
- The preview modal and download action use the original object URL, not the
  thumbnail URL.

## Current API Behavior

Thumbnail generation and serving are implemented, but clients still need to keep
the thumbnail/original split clear when adding new views.

| Endpoint | Current behavior | UI usage |
|---|---|---|
| `GET /api/gallery` | Returns `url` and `thumbnail_url` per item | Grid should render `thumbnail_url`, with `url` only as a fallback. |
| `GET /api/search?q=...` | Returns `metadata.url` and `metadata.thumbnail_url` per result | Grid should render `thumbnail_url`, with `url` only as a fallback. |
| `GET /api/clusters` | Returns `url` and `thumbnail_url` for sample images | Cluster cards should render `thumbnail_url`, with `url` only as a fallback. |
| `GET /api/cluster/{cluster_id}` | Returns `url` and `thumbnail_url` for member images | Member grids should render `thumbnail_url`, with `url` only as a fallback. |
| `GET /api/people` and `GET /api/people/{person_id}/images` | Return thumbnail URLs for person and media previews | People grids should render thumbnail URLs. |
| `GET /api/image/{media_id}` | Returns image detail JSON, including original `url` and `thumbnail_url` | Preview modal can use the original `url` for inspection/download. |
| `GET /api/image/{media_id}/thumbnail` | Redirects to the stored thumbnail when present, otherwise falls back to the original | Safe default for grid/list image elements. |
| `POST /api/thumbnails/backfill` | Queues thumbnail generation for existing media without thumbnails | Maintenance action; not used for normal image rendering. |

## See Also

- [README - Architecture](../../README.md#architecture)
- [README - Key endpoints](../../README.md#key-endpoints)
