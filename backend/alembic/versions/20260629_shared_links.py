"""Add shared_links table (public capability-URL access to an album).

Security: stores only the SHA-256 hash of the access key and an optional
bcrypt password hash — never plaintext (diverges from the reference).

Revision ID: 20260629sharedlinks
Revises: 20260629albums
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260629sharedlinks"
down_revision = "20260629albums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "album_id",
            sa.Integer(),
            sa.ForeignKey("albums.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "allow_download",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "show_exif",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_shared_links_key_hash", "shared_links", ["key_hash"], unique=True
    )
    op.create_index("ix_shared_links_album_id", "shared_links", ["album_id"])
    op.create_index("ix_shared_links_owner_user_id", "shared_links", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_shared_links_owner_user_id", table_name="shared_links")
    op.drop_index("ix_shared_links_album_id", table_name="shared_links")
    op.drop_index("ix_shared_links_key_hash", table_name="shared_links")
    op.drop_table("shared_links")
