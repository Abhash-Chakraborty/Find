# Image Loading Behavior: Thumbnails vs Full Resolution

This document describes the intended image loading strategy in Find — specifically how thumbnails are used in grid/list views while full-resolution images are reserved for the preview modal and downloads.

## Overview

Find serves images in two distinct modes depending on context:

- **Thumbnails** — small, optimized variants used everywhere images appear in a grid or list.
- **Full-resolution originals** — the unmodified source file, used only in the preview modal and when downloading.

This distinction matters for performance. Loading full-size images across an entire gallery or search results page puts unnecessary pressure on MinIO, network bandwidth, and the browser's rendering pipeline, making the UI feel heavy. Using small thumbnails in grid contexts keeps the experience fast without sacrificing quality where it counts.

## Where Each Image Size Is Used

### Thumbnail views (small images)

The following views should display thumbnail-sized images rather than originals:

- **Gallery** (`GET /api/gallery`) — the main image grid on the home/gallery page.
- **Search results** (`GET /api/search?q=...`) — the grid of results returned for a natural-language query.
- **Clusters page** (`GET /api/clusters`) — the cluster overview grid showing representative images per cluster.
- **Cluster detail** (`GET /api/cluster/{cluster_id}`) — the member image grid inside a single cluster.
- **People page** — any person-grouped views that display small face or image thumbnails.

In all these views, the goal is to render many images simultaneously without fetching large files.

### Full-resolution views

- **Preview modal** — when a user clicks an image to inspect it in detail, the full original is loaded.
- **Download** — the file served for download should always be the original, uncompressed source.

## Quality Preservation

Thumbnail generation must not alter or degrade the original image stored in MinIO. The original file is the source of truth and should remain untouched. Thumbnails are derived copies produced separately, sized appropriately for their display context (exact dimensions to be defined during implementation).

This means:

- The original uploaded file is stored as-is in MinIO.
- Thumbnails are generated from the original without modifying or replacing it.
- The preview modal and download endpoint always reference the original MinIO object, not the thumbnail.

## Implementation Note

Thumbnail generation itself is **out of scope for this document**. This page documents the intended behavior to give contributors the context needed to understand why current full-image loading is a known performance gap, and what the target state looks like. Implementation tracking issues will be linked here once available.

## Related Endpoints

| Endpoint | Current behavior | Intended behavior |
|---|---|---|
| `GET /api/gallery` | Returns full-resolution URLs | Should return thumbnail URLs |
| `GET /api/search?q=...` | Returns full-resolution URLs | Should return thumbnail URLs |
| `GET /api/clusters` | Returns full-resolution URLs | Should return thumbnail URLs |
| `GET /api/cluster/{cluster_id}` | Returns full-resolution URLs | Should return thumbnail URLs |
| `GET /api/image/{media_id}` | Returns full-resolution image | Retain full-resolution for modal/download |

## See Also

- [README — Architecture](../README.md#architecture)
- [README — Key endpoints](../README.md#key-endpoints)
- Implementation issues: *(links to be added once available)*
