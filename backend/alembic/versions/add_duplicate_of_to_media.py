"""add duplicate_of to media

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "add_dup_of_media_001"
down_revision = "20260521hiddenvault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "duplicate_of",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_media_duplicate_of", "media", ["duplicate_of"])


def downgrade() -> None:
    op.drop_index("ix_media_duplicate_of", table_name="media")
    op.drop_column("media", "duplicate_of")
