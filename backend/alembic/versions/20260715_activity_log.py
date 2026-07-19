"""Add activity table (append-only local activity log).

Revision ID: 20260715activitylog
Revises: 20260714_vault_credentials
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260715activitylog"
down_revision = "20260714_vault_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "media_id",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index("ix_activity_category", "activity", ["category"])
    op.create_index("ix_activity_action", "activity", ["action"])
    op.create_index("ix_activity_user_id", "activity", ["user_id"])
    op.create_index("ix_activity_media_id", "activity", ["media_id"])
    op.create_index("ix_activity_created_at", "activity", ["created_at"])
    op.create_index("ix_activity_user_created", "activity", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_user_created", table_name="activity")
    op.drop_index("ix_activity_created_at", table_name="activity")
    op.drop_index("ix_activity_media_id", table_name="activity")
    op.drop_index("ix_activity_user_id", table_name="activity")
    op.drop_index("ix_activity_action", table_name="activity")
    op.drop_index("ix_activity_category", table_name="activity")
    op.drop_table("activity")
