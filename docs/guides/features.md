# Features Guide

A tour of Find's photo-management features in the React web UI. Each section
maps to a route reachable from the top navigation.

## Timeline (`/timeline`)

A fast, date-organized view of your whole library.

- **Justified grid** — photos are laid out in rows that fill the width while
  preserving each photo's aspect ratio, and only the on-screen rows are
  rendered, so large libraries stay smooth.
- **Date scrubber** — the vertical scrollbar on the right shows the current
  month and lets you jump to any date; hovering/dragging previews the month
  under the cursor.
- **Favorites filter** — the "Show favorites" toggle limits the timeline to
  liked photos.
- **Asset viewer** — click any photo to open the full-screen viewer:
  - zoom (`+`/`-`, double-click) and pan (drag while zoomed),
  - next/previous (`←`/`→` or the on-screen arrows),
  - slideshow (play/pause; `Space`),
  - favorite (♡), archive, and move-to-trash actions,
  - `Esc` closes the viewer (or exits zoom first).

## Albums (`/albums`)

Collections of photos with a cover and manual ordering.

- **Create** an album from the list page; **open** one to see its photos.
- **Add photos** from the gallery: select photos, then "Add to album" (pick an
  existing album or create one on the spot).
- In an album you can **set a cover** (any member), **remove** photos,
  **reorder**, **open the viewer**, and **delete** the album.

## Sharing

Share an album via a public link — no account needed to view.

- On an album's page, **create a share link**. You can optionally set a
  **password** and choose whether viewers may **download** originals.
- The link opens a public, read-only album view (`/public/shared/<key>`); if a
  password was set, viewers are prompted for it.
- **Revoke** a link at any time from the album page.
- Security: the link key and any password are stored hashed (never in clear
  text), links can expire, and a viewer only ever sees the linked album — never
  your wider library. With download disabled, only thumbnails are served.

## Favorites, Archive & Trash

- **Favorite** (♡) marks photos you love; the timeline favorites toggle and the
  gallery's liked filter surface them.
- **Archive** (`/archive`) keeps photos out of the main timeline without
  deleting them. Archive from the gallery selection bar or the viewer;
  unarchive from the archive page.
- **Trash** (`/trash`) is a recoverable soft-delete. Trash from the gallery or
  viewer; **restore** individual items, or **empty trash** to delete
  permanently. Trashed items older than the retention window
  (`TRASH_RETENTION_DAYS`, default 30) are eligible for auto-purge.
- Archived and trashed photos are automatically excluded from the timeline,
  search, and albums until restored.

> Note: the gallery's existing **Delete** remains a permanent delete. Trash is a
> separate, recoverable path.

## Settings (`/settings`)

- **Hardware acceleration** — choose `Auto`, `GPU`, or `CPU`. The panel shows
  what hardware was detected and which device is actually in use, and surfaces
  a notice if a requested GPU isn't available (Find falls back to CPU
  automatically). See the [Hardware Acceleration](hardware-acceleration.md)
  guide for details.
