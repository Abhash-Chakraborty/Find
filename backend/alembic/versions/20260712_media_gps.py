"""Add opt-in GPS coordinates for the private map.

Revision ID: 20260712mediagps
Revises: 20260630partnershares
"""

from alembic import op
import sqlalchemy as sa


revision = "20260712mediagps"
down_revision = "20260630partnershares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("media", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_index("ix_media_latitude", "media", ["latitude"])
    op.create_index("ix_media_longitude", "media", ["longitude"])


def downgrade() -> None:
    op.drop_index("ix_media_longitude", table_name="media")
    op.drop_index("ix_media_latitude", table_name="media")
    op.drop_column("media", "longitude")
    op.drop_column("media", "latitude")
