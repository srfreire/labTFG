"""Tests for shared.artifacts.register_artifact.

Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.artifacts import register_artifact
from shared.database import DatabaseService
from shared.models import Artifact, Base, Experiment, Run
from shared.settings import Settings, load_settings

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
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def db_global(engine):
    """Provide a connected DatabaseService for register_artifact."""
    settings = Settings(POSTGRES_DSN=DSN)
    db = DatabaseService(settings)
    await db.connect()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_register_artifact_with_run(session, db_global):
    """register_artifact persists with run_id linkage."""
    run = Run(problem_description="art test", s3_prefix="r/")
    session.add(run)
    await session.commit()

    await register_artifact(
        s3_key=f"artifacts/{uuid.uuid4()}.txt",
        artifact_type="report",
        size_bytes=100,
        run_id=str(run.id),
        db=db_global,
    )

    result = await session.execute(select(Artifact).where(Artifact.run_id == run.id))
    fetched = result.scalar_one()
    assert fetched.size_bytes == 100
    assert fetched.artifact_type == "report"
    assert fetched.content_type == "text/plain"  # default
    assert fetched.experiment_id is None


@pytest.mark.asyncio
async def test_register_artifact_with_experiment(session, db_global):
    """register_artifact persists with experiment_id linkage."""
    exp = Experiment(description="exp")
    session.add(exp)
    await session.commit()

    await register_artifact(
        s3_key=f"artifacts/{uuid.uuid4()}.bin",
        artifact_type="binary",
        size_bytes=2048,
        content_type="application/octet-stream",
        experiment_id=str(exp.id),
        db=db_global,
    )

    result = await session.execute(
        select(Artifact).where(Artifact.experiment_id == exp.id)
    )
    fetched = result.scalar_one()
    assert fetched.run_id is None
    assert fetched.size_bytes == 2048
    assert fetched.content_type == "application/octet-stream"


@pytest.mark.asyncio
async def test_register_artifact_no_links(session, db_global):
    """register_artifact may have neither run nor experiment id."""
    s3_key = f"artifacts/orphan-{uuid.uuid4()}.txt"
    await register_artifact(
        s3_key=s3_key,
        artifact_type="misc",
        size_bytes=1,
        db=db_global,
    )

    result = await session.execute(select(Artifact).where(Artifact.s3_key == s3_key))
    fetched = result.scalar_one()
    assert fetched.run_id is None
    assert fetched.experiment_id is None


@pytest.mark.asyncio
async def test_register_artifact_string_uuids_converted(session, db_global):
    """run_id/experiment_id may be passed as strings; they're converted to UUID."""
    run = Run(problem_description="conv", s3_prefix="r/")
    session.add(run)
    await session.commit()

    # run.id is a UUID; string form should still resolve correctly
    await register_artifact(
        s3_key=f"artifacts/conv-{uuid.uuid4()}.txt",
        artifact_type="r",
        size_bytes=5,
        run_id=str(run.id),
        db=db_global,
    )

    result = await session.execute(select(Artifact).where(Artifact.run_id == run.id))
    fetched = result.scalar_one()
    assert isinstance(fetched.run_id, uuid.UUID)
