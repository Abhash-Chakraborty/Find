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

## Gallery Performance Target

For a local library with 1,000 indexed images on a typical contributor laptop,
common gallery interactions should remain comfortably interactive:

- Initial gallery, search, cluster, and people grid render should mount only the
  visible rows plus a small overscan buffer.
- Loading another page of gallery or search results should complete without
  mounting every previously loaded card again.
- Scrolling a loaded grid should keep the main thread responsive, with no long
  tasks above 100 ms during normal browsing.
- Preview and download actions should continue to use the full-resolution
  original, even when the card that opened the preview was rendered from a
  thumbnail.

Implementation tracking:

| Work area | Status |
|---|---|
| Thumbnail generation during image analysis | Implemented in the worker thumbnail path and backfill job. |
| API thumbnail URLs for gallery/search/clusters/people | Implemented through `thumbnail_url` fields and `/api/image/{id}/thumbnail`. |
| Frontend thumbnail usage in grid views | Grid views prefer `thumbnail_url`; preview/download flows use original URLs. |
| Grid virtualization/pagination tuning | Gallery/search/clusters/people use paginated API calls where available and dependency-free row virtualization in large grids. |

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

## Manual Benchmark

Run this before and after gallery rendering changes:

1. Seed or upload at least 1,000 local images, then ensure thumbnails are present
   by running the normal analysis flow or `POST /api/thumbnails/backfill`.
2. Open browser DevTools Performance, enable screenshots, and throttle nothing.
3. Record the Gallery page while loading the first page, clicking `Load more`
   until at least 120 items are loaded, scrolling from top to bottom, opening a
   preview, and downloading one image.
4. Repeat for Search results, Cluster detail, and a People detail modal when the
   data set has enough matching images.
5. Confirm grid images request thumbnail URLs, preview/download requests use
   original URLs, visible card counts stay bounded while scrolling, and no normal
   browse interaction produces a long task above 100 ms.

## See Also

- [README - Architecture](../../README.md#architecture)
- [README - Key endpoints](../../README.md#key-endpoints)
