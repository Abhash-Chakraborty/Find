"""add HNSW index on media.vector for fast similarity search

Without this index every semantic search and every per-upload near-duplicate
check does a full sequential scan computing cosine distance for every row.
An HNSW index turns those O(N) scans into approximate O(log N) lookups.

Revision ID: hnsw_vector_idx_001
Revises: add_dup_of_media_001
Create Date: 2026-06-28
"""

from alembic import op

revision = "hnsw_vector_idx_001"
down_revision = "add_dup_of_media_001"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_media_vector_hnsw"


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    # pgvector-specific; skip on other backends (e.g. sqlite test DBs).
    if not _is_postgresql():
        return

    # HNSW with cosine ops matches the `<=>` operator used by search.py and
    # duplicate_service.py. Requires pgvector >= 0.5.0 (shipped by the
    # ankane/pgvector image). IF NOT EXISTS keeps the migration idempotent.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_INDEX_NAME} "
        "ON media USING hnsw (vector vector_cosine_ops)"
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
