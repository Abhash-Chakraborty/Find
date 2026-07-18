"""Add album tables (albums + album_assets).

Albums are collections of media with a cover and manual ordering. Sharing
roles and the activity feed are out of scope here (later stages).

Revision ID: 20260629albums
Revises: 20260629assetstate
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260629albums"
down_revision = "20260629assetstate"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "albums",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            server_default="Untitled Album",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "cover_media_id",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_albums_cover_media_id", "albums", ["cover_media_id"])
    op.create_index("ix_albums_owner_user_id", "albums", ["owner_user_id"])

    op.create_table(
        "album_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "album_id",
            sa.Integer(),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "media_id",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.UniqueConstraint("album_id", "media_id", name="uq_album_asset"),
    )
    op.create_index("ix_album_assets_album_id", "album_assets", ["album_id"])
    op.create_index("ix_album_assets_media_id", "album_assets", ["media_id"])
    op.create_index(
        "ix_album_assets_album_position", "album_assets", ["album_id", "position"]
    )


def downgrade() -> None:
    op.drop_index("ix_album_assets_album_position", table_name="album_assets")
    op.drop_index("ix_album_assets_media_id", table_name="album_assets")
    op.drop_index("ix_album_assets_album_id", table_name="album_assets")
    op.drop_table("album_assets")
    op.drop_index("ix_albums_owner_user_id", table_name="albums")
    op.drop_index("ix_albums_cover_media_id", table_name="albums")
    op.drop_table("albums")
