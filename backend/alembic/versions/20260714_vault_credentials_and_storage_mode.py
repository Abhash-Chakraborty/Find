"""Add recoverable password-gated vault storage mode.

Revision ID: 20260714_vault_credentials
Revises: 20260712_media_gps
"""

from alembic import op
import sqlalchemy as sa

revision = "20260714_vault_credentials"
down_revision = "20260712mediagps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vault_config", sa.Column("recovery_code_hash", sa.String(255), nullable=True)
    )
    op.add_column(
        "vault_config",
        sa.Column(
            "storage_mode", sa.String(32), nullable=False, server_default="protected"
        ),
    )


def downgrade() -> None:
    op.drop_column("vault_config", "storage_mode")
    op.drop_column("vault_config", "recovery_code_hash")
