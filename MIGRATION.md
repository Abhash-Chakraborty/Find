# Migration Notes — App Overhaul

Upgrade steps for the `feat/app-overhaul` changes. These cover database schema
and one new environment variable. The overhaul is designed to be **additive and
non-breaking**: existing media stays visible, and the existing delete behavior
is unchanged.

## 1. Database migrations

Three Alembic migrations are added, chained off the prior head into a single
new head (`20260629sharedlinks`):

1. `20260629_asset_state_columns` — adds `media.is_archived` (bool, default
   false) and `media.deleted_at` (nullable timestamp), plus indexes. Also a
   merge point for the two prior Alembic heads.
2. `20260629_albums` — adds the `albums` and `album_assets` tables.
3. `20260629_shared_links` — adds the `shared_links` table.

Apply them with:

```bash
cd backend
uv run alembic upgrade head
```

Each migration has a `downgrade()` for rollback.

> **PostgreSQL note:** Find's `init_db()` also runs an idempotent schema
> normalizer on startup (`ADD COLUMN IF NOT EXISTS …`) that mirrors the
> asset-state columns, so a fresh start on an existing Postgres database will
> self-heal even before Alembic runs. Alembic remains the source of truth for
> version history.

### What the new columns/tables mean
- `media.is_archived` / `media.deleted_at`: drive the Archive and Trash views.
  Both default to the "visible" state, so **all existing media remains in the
  main timeline** after migrating.
- `albums` / `album_assets`: album metadata, cover, and membership (with manual
  ordering position).
- `shared_links`: public album share links. Stores only a **hash** of the access
  key and an optional **bcrypt** password hash — never plaintext.

## 2. New environment variable

```bash
# Hardware acceleration mode for ML inference: auto | gpu | cpu (default: auto)
ACCEL_MODE=auto
```

- `auto` — use the best available accelerator, else CPU (recommended default).
- `gpu` — prefer GPU; **automatically falls back to CPU** if none is available.
- `cpu` — force CPU.

The legacy `USE_GPU=false` is still honored as a hard CPU pin when `ACCEL_MODE`
is left at `auto`. See `docs/guides/hardware-acceleration.md`.

No value is required — omitting `ACCEL_MODE` behaves exactly as before for
GPU-equipped hosts and now also works cleanly on CPU-only machines.

## 3. Behavior compatibility

- **Delete is unchanged.** `DELETE /api/image/{id}` and the bulk-delete endpoint
  remain permanent hard-deletes. Trash (soft delete) is a separate, additive
  flow (`POST /api/image/{id}/trash`); emptying the trash is the only new path
  that permanently deletes.
- **Gallery/search scoping.** These now exclude archived and trashed assets in
  addition to hidden ones. Because the new columns default to visible, existing
  libraries see no change until a user archives or trashes something.
- **No frontend route removed.** New routes (`/timeline`, `/albums`, `/archive`,
  `/trash`, `/settings`, `/public/shared/[key]`) are added and linked in the nav.

## 4. Rollback

The asset-state migration is a **merge point** of the two prior Alembic heads
(`20260528vaultstate` and `hnsw_vector_idx_001`). Downgrading past it restores
both of those heads (the pre-overhaul state):

```bash
cd backend
# Reverts shared_links, albums, and asset-state columns. Restores the two
# prior heads; run `uv run alembic heads` afterward to confirm.
uv run alembic downgrade 20260528vaultstate
```

Then unset `ACCEL_MODE` (or leave it — it is ignored by pre-overhaul code).
