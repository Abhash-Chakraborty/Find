"""Add hidden vault schema.

Revision ID: 20260521hiddenvault
Revises:
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260521hiddenvault"
down_revision = None
branch_labels = None
depends_on = None


def _created_at_default():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("now()")
    return sa.text("CURRENT_TIMESTAMP")


def _hidden_default():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("false")
    return sa.text("0")


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=_hidden_default(),
        ),
    )

    op.create_table(
        "vault_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("salt", sa.LargeBinary(), nullable=False),
        sa.Column("verifier_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("verifier_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_created_at_default(),
        ),
        sa.CheckConstraint("id = 1", name="ck_vault_config_singleton"),
    )

    op.create_table(
        "vault_metadata",
        sa.Column(
            "media_id",
            sa.Integer(),
            sa.ForeignKey("media.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("encrypted_path", sa.Text(), nullable=False),
        sa.Column("iv", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_created_at_default(),
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_media_is_hidden_false",
            "media",
            ["is_hidden"],
            postgresql_where=sa.text("is_hidden = false"),
        )
    else:
        op.create_index(
            "ix_media_is_hidden",
            "media",
            ["is_hidden"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    index_name = (
        "ix_media_is_hidden_false"
        if bind.dialect.name == "postgresql"
        else "ix_media_is_hidden"
    )
    op.drop_index(index_name, table_name="media")

    op.drop_table("vault_metadata")
    op.drop_table("vault_config")

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("media") as batch_op:
            batch_op.drop_column("is_hidden")
    else:
        op.drop_column("media", "is_hidden")
