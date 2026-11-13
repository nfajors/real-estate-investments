"""Alembic environment. The database URL comes from AXIOM_MIGRATION_DATABASE_URL (owner role)
or AXIOM_DATABASE_URL."""

import os

from alembic import context
from app import models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from sqlalchemy import create_engine, pool

target_metadata = Base.metadata


def _url() -> str:
    return os.environ.get("AXIOM_MIGRATION_DATABASE_URL") or os.environ.get("AXIOM_DATABASE_URL",
                                                                           "sqlite:///./axiom.db")


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
