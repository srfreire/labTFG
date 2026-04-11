"""Alembic env.py — async migrations for labtfg."""
import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from shared.models import Base

config = context.config

dsn = os.environ.get("POSTGRES_DSN", config.get_main_option("sqlalchemy.url"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=dsn, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(dsn)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
