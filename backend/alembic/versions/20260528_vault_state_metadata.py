"""Add vault state metadata fields.

Revision ID: 20260528vaultstate
Revises: add_dup_of_media_001
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260528vaultstate"
down_revision = "add_dup_of_media_001"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "vault_state",
            sa.String(length=32),
            nullable=False,
            server_default="visible",
        ),
    )
    op.add_column(
        "media",
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "media",
        sa.Column("encrypted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_media_vault_state", "media", ["vault_state"])

    op.add_column(
        "vault_metadata",
        sa.Column(
            "encryption_algorithm",
            sa.String(length=64),
            nullable=False,
            server_default="AES-256-GCM",
        ),
    )
    op.add_column(
        "vault_metadata",
        sa.Column("key_derivation", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "vault_metadata",
        sa.Column("ciphertext_size", sa.Integer(), nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE media SET vault_state = CASE "
            "WHEN is_hidden THEN 'hidden_encrypted' ELSE 'visible' END "
        )
    )
    op.execute(
        sa.text(
            "UPDATE media SET hidden_at = created_at "
            "WHERE is_hidden = true AND hidden_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE media SET encrypted_at = hidden_at "
            "WHERE is_hidden = true AND encrypted_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_media_vault_state", table_name="media")

    if _is_sqlite():
        with op.batch_alter_table("vault_metadata") as batch_op:
            batch_op.drop_column("ciphertext_size")
            batch_op.drop_column("key_derivation")
            batch_op.drop_column("encryption_algorithm")
        with op.batch_alter_table("media") as batch_op:
            batch_op.drop_column("encrypted_at")
            batch_op.drop_column("hidden_at")
            batch_op.drop_column("vault_state")
    else:
        op.drop_column("vault_metadata", "ciphertext_size")
        op.drop_column("vault_metadata", "key_derivation")
        op.drop_column("vault_metadata", "encryption_algorithm")
        op.drop_column("media", "encrypted_at")
        op.drop_column("media", "hidden_at")
        op.drop_column("media", "vault_state")
