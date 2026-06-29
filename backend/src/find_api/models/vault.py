"""Vault persistence models."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.sql import func

from find_api.core.database import Base


class VaultConfig(Base):
    """Singleton vault configuration and verifier material."""

    __tablename__ = "vault_config"

    id = Column(Integer, primary_key=True)
    salt = Column(LargeBinary, nullable=False)
    verifier_nonce = Column(LargeBinary, nullable=False)
    verifier_ciphertext = Column(LargeBinary, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (CheckConstraint("id = 1", name="ck_vault_config_singleton"),)


class VaultMetadata(Base):
    """Per-media encrypted vault blob metadata."""

    __tablename__ = "vault_metadata"

    media_id = Column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_path = Column(Text, nullable=False)
    iv = Column(LargeBinary, nullable=False)
    encryption_algorithm = Column(
        String(64), nullable=False, server_default="AES-256-GCM"
    )
    key_derivation = Column(String(128), nullable=True)
    ciphertext_size = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
