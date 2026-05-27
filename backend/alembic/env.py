from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import find_api.core.database as database_module  # noqa: E402
import find_api.models as models_module  # noqa: E402

if not hasattr(database_module, "SQLALCHEMY_DATABASE_URL"):
    database_module.SQLALCHEMY_DATABASE_URL = database_module.settings.DATABASE_URL
if not hasattr(models_module, "Base"):
    models_module.Base = database_module.Base

from find_api.core.database import SQLALCHEMY_DATABASE_URL  # noqa: E402
from find_api.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=SQLALCHEMY_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
