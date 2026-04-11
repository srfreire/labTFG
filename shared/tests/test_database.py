"""Tests for SQLAlchemy models and DatabaseService.

Requires docker-compose Postgres running on localhost:5432.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared.database import DatabaseService
from shared.models import Artifact, Base, Experiment, Model, Run
from shared.settings import Settings

DSN = "postgresql+asyncpg://labtfg:labtfg@localhost:5432/labtfg"


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
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.mark.asyncio
async def test_database_service_connect():
    settings = Settings(POSTGRES_DSN=DSN)
    db = DatabaseService(settings)
    await db.connect()
    async with db.get_session() as sess:
        assert isinstance(sess, AsyncSession)
    await db.close()


@pytest.mark.asyncio
async def test_insert_and_query_run(session: AsyncSession):
    run = Run(
        problem_description="Test problem",
        status="created",
        s3_prefix="runs/test/",
    )
    session.add(run)
    await session.commit()

    assert run.id is not None
    assert isinstance(run.id, uuid.UUID)

    from sqlalchemy import select

    result = await session.execute(select(Run).where(Run.id == run.id))
    fetched = result.scalar_one()
    assert fetched.problem_description == "Test problem"
    assert fetched.status == "created"


@pytest.mark.asyncio
async def test_insert_model_with_fk_to_run(session: AsyncSession):
    run = Run(
        problem_description="FK test",
        s3_prefix="runs/fk/",
    )
    session.add(run)
    await session.commit()

    model = Model(
        formulation_id="test-model-001",
        class_name="TestModel",
        paradigm="prisoner_dilemma",
        run_id=run.id,
        s3_model_key="models/test-model-001.py",
    )
    session.add(model)
    await session.commit()

    from sqlalchemy import select

    result = await session.execute(
        select(Model).where(Model.formulation_id == "test-model-001")
    )
    fetched = result.scalar_one()
    assert fetched.run_id == run.id
    assert fetched.class_name == "TestModel"


@pytest.mark.asyncio
async def test_insert_experiment_with_jsonb(session: AsyncSession):
    spec = {
        "grid_width": 10,
        "grid_height": 10,
        "resources": [{"type": "food", "x": 5, "y": 5}],
    }
    experiment = Experiment(
        description="JSONB test experiment",
        spec=spec,
        models_used={"model_a": "v1", "model_b": "v2"},
        steps=100,
        seed=42,
    )
    session.add(experiment)
    await session.commit()

    from sqlalchemy import select

    result = await session.execute(
        select(Experiment).where(Experiment.id == experiment.id)
    )
    fetched = result.scalar_one()
    assert fetched.spec == spec
    assert fetched.steps == 100
    assert fetched.seed == 42


@pytest.mark.asyncio
async def test_insert_artifact_with_fks(session: AsyncSession):
    run = Run(
        problem_description="Artifact FK test",
        s3_prefix="runs/artifact/",
    )
    experiment = Experiment(description="Artifact experiment")
    session.add_all([run, experiment])
    await session.commit()

    artifact = Artifact(
        s3_key="artifacts/test-report.pdf",
        artifact_type="report",
        run_id=run.id,
        experiment_id=experiment.id,
        size_bytes=12345,
        content_type="application/pdf",
    )
    session.add(artifact)
    await session.commit()

    from sqlalchemy import select

    result = await session.execute(
        select(Artifact).where(Artifact.id == artifact.id)
    )
    fetched = result.scalar_one()
    assert fetched.run_id == run.id
    assert fetched.experiment_id == experiment.id
    assert fetched.size_bytes == 12345
    assert fetched.content_type == "application/pdf"


@pytest.mark.asyncio
async def test_jsonb_round_trip(session: AsyncSession):
    nested = {
        "level1": {
            "level2": [1, 2, {"level3": True}],
        },
        "tags": ["a", "b", "c"],
        "count": 42,
    }
    experiment = Experiment(
        description="JSONB round-trip",
        spec=nested,
    )
    session.add(experiment)
    await session.commit()

    # Save id before expiring, then clear cache to force DB read
    exp_id = experiment.id
    session.expire_all()

    from sqlalchemy import select

    result = await session.execute(
        select(Experiment).where(Experiment.id == exp_id)
    )
    fetched = result.scalar_one()
    assert fetched.spec == nested
    assert fetched.spec["level1"]["level2"][2]["level3"] is True
