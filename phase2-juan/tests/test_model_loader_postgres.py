"""Integration test: model_loader.discover_models reads from real Postgres.

Requires docker-compose Postgres running on localhost:5432. The test inserts a
`Model` row, hands the live ``DatabaseService`` to the loader, and verifies the
loader sees the row through the same async session machinery the orchestrator
uses in production.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from simlab.model_loader import discover_models
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.models import Base, Model, Run
from shared.settings import load_settings

pytestmark = pytest.mark.integration


DSN = load_settings().POSTGRES_DSN


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(DSN)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db_with_engine(engine):
    """A DatabaseService-shaped object backed by the test engine.

    Mirrors `shared.database.DatabaseService.get_session` exactly: an
    `@asynccontextmanager` that yields a session from the factory.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class _TestDB:
        @asynccontextmanager
        async def get_session(self):
            async with factory() as session:
                yield session

    return _TestDB()


@pytest.mark.asyncio
async def test_discover_models_reads_from_postgres(engine, db_with_engine):
    """End-to-end: insert a Model row, discover_models picks it up via PG."""
    run_id = uuid.uuid4()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            Run(id=run_id, problem_description="loader-test", s3_prefix="loader/")
        )
        session.add(
            Model(
                class_name="DriveReductionRLModel",
                paradigm="homeostatic-regulation",
                formulation="drive-reduction-rl",
                description="Loader integration",
                run_id=run_id,
                s3_model_key="models/loader-test/drive-reduction-rl_model.py",
            )
        )
        await session.commit()

    models = await discover_models(db=db_with_engine)

    key = "homeostatic-regulation/drive-reduction-rl"
    assert key in models
    info = models[key]
    assert info.class_name == "DriveReductionRLModel"
    assert info.description == "Loader integration"
    assert info.run_id == str(run_id)
    assert info.s3_model_key == ("models/loader-test/drive-reduction-rl_model.py")


@pytest.mark.asyncio
async def test_discover_models_empty_table(db_with_engine):
    """No rows → empty dict, no errors."""
    models = await discover_models(db=db_with_engine)
    assert models == {}
