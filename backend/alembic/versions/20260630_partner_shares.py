"""Add partner_shares table (directed user-to-user read sharing).

Revision ID: 20260630partnershares
Revises: 20260630appsettings
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260630partnershares"
down_revision = "20260630appsettings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sharer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "partner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "sharer_user_id", "partner_user_id", name="uq_partner_share_pair"
        ),
    )
    op.create_index(
        "ix_partner_shares_sharer_user_id", "partner_shares", ["sharer_user_id"]
    )
    op.create_index(
        "ix_partner_shares_partner_user_id", "partner_shares", ["partner_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_partner_shares_partner_user_id", table_name="partner_shares")
    op.drop_index("ix_partner_shares_sharer_user_id", table_name="partner_shares")
    op.drop_table("partner_shares")
