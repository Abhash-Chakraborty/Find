"""Add asset-state columns (archive + soft-delete/trash) to media.

Adds:
- ``is_archived`` BOOLEAN NOT NULL DEFAULT false — archived assets are kept
  but excluded from the main timeline/search.
- ``deleted_at`` TIMESTAMP WITH TIME ZONE NULL — soft-delete marker; non-null
  means the asset is in the trash and is excluded from browse surfaces.

Also merges the two existing Alembic heads (``20260528vaultstate`` and
``hnsw_vector_idx_001``) into a single head.

Revision ID: 20260629assetstate
Revises: 20260528vaultstate, hnsw_vector_idx_001
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260629assetstate"
down_revision = ("20260528vaultstate", "hnsw_vector_idx_001")
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "media",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_is_archived", "media", ["is_archived"])
    op.create_index("ix_media_deleted_at", "media", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_media_deleted_at", table_name="media")
    op.drop_index("ix_media_is_archived", table_name="media")

    if _is_sqlite():
        with op.batch_alter_table("media") as batch_op:
            batch_op.drop_column("deleted_at")
            batch_op.drop_column("is_archived")
    else:
        op.drop_column("media", "deleted_at")
        op.drop_column("media", "is_archived")
