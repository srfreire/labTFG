"""Constraint and default-value tests for shared.models ORM.

Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.models import (
    Artifact,
    Base,
    Experiment,
    Model,
    NodeRunObservation,
    Run,
    SimulationObservation,
)
from shared.models import (
    PipelineMemory as Memory,
)
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
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.mark.asyncio
async def test_model_unique_constraint_enforced(session):
    """UniqueConstraint(run_id, paradigm, formulation) rejects duplicates."""
    run = Run(problem_description="uc", s3_prefix="r/")
    session.add(run)
    await session.commit()
    run_id = run.id

    m1 = Model(
        class_name="A",
        paradigm="hedonic",
        formulation="q-learning",
        run_id=run_id,
        s3_model_key="m1",
    )
    session.add(m1)
    await session.commit()

    m2 = Model(
        class_name="B",
        paradigm="hedonic",
        formulation="q-learning",
        run_id=run_id,
        s3_model_key="m2",
    )
    session.add(m2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_artifact_s3_key_unique(session):
    """Artifact.s3_key has a unique constraint."""
    a1 = Artifact(
        s3_key="artifacts/dup.txt",
        artifact_type="x",
        size_bytes=1,
        content_type="text/plain",
    )
    session.add(a1)
    await session.commit()

    a2 = Artifact(
        s3_key="artifacts/dup.txt",
        artifact_type="x",
        size_bytes=2,
        content_type="text/plain",
    )
    session.add(a2)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_run_default_status_is_created(session):
    run = Run(problem_description="status", s3_prefix="r/")
    session.add(run)
    await session.commit()
    run_id = run.id
    session.expire_all()
    result = await session.execute(select(Run.status).where(Run.id == run_id))
    assert result.scalar_one() == "created"


@pytest.mark.asyncio
async def test_experiment_default_status_is_created(session):
    exp = Experiment(description="exp default")
    session.add(exp)
    await session.commit()
    exp_id = exp.id
    session.expire_all()
    result = await session.execute(
        select(Experiment.status).where(Experiment.id == exp_id)
    )
    assert result.scalar_one() == "created"


@pytest.mark.asyncio
async def test_pipeline_memory_defaults(session):
    """PipelineMemory has sensible defaults for counters and timestamps."""
    run = Run(problem_description="defaults", s3_prefix="r/")
    session.add(run)
    await session.commit()

    mem = Memory(
        content="defaults",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run.id,
        importance=5.0,
        confidence=0.8,
    )
    session.add(mem)
    await session.commit()
    mem_id = mem.id

    session.expire_all()
    result = await session.execute(
        select(
            Memory.access_count,
            Memory.corroborations,
            Memory.contradictions,
            Memory.valid_from,
            Memory.valid_to,
            Memory.last_accessed_at,
        ).where(Memory.id == mem_id)
    )
    row = result.one()
    assert row.access_count == 0
    assert row.corroborations == 0
    assert row.contradictions == 0
    assert row.valid_from is not None
    assert row.valid_to is None
    assert row.last_accessed_at is None


@pytest.mark.asyncio
async def test_pipeline_memory_self_supersession(session):
    """PipelineMemory.superseded_by is a self-referencing FK."""
    run = Run(problem_description="self-supers", s3_prefix="r/")
    session.add(run)
    await session.commit()

    a = Memory(
        content="v1",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run.id,
        importance=5.0,
        confidence=0.8,
    )
    session.add(a)
    await session.commit()
    a_id = a.id

    b = Memory(
        content="v2",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run.id,
        importance=5.0,
        confidence=0.85,
        superseded_by=a_id,  # b points to a
    )
    session.add(b)
    await session.commit()
    b_id = b.id

    session.expire_all()
    result = await session.execute(
        select(Memory.superseded_by).where(Memory.id == b_id)
    )
    assert result.scalar_one() == a_id


@pytest.mark.asyncio
async def test_pipeline_memory_indexes_present(engine):
    """All declared indexes exist on the pipeline_memories table."""
    async with engine.begin() as conn:

        def _list_indexes(sync_conn) -> set[str]:
            insp = inspect(sync_conn)
            return {idx["name"] for idx in insp.get_indexes("pipeline_memories")}

        names = await conn.run_sync(_list_indexes)

    expected = {
        "ix_pipeline_memories_namespace",
        "ix_pipeline_memories_run_id",
        "ix_pipeline_memories_source_stage",
        "ix_pipeline_memories_confidence",
        "ix_pipeline_memories_valid_to",
        "ix_pipeline_memories_ns_confidence",
    }
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_simulation_observation_indexes_present(engine):
    """All declared indexes exist on the simulation_observations table."""
    async with engine.begin() as conn:

        def _list_indexes(sync_conn) -> set[str]:
            insp = inspect(sync_conn)
            return {idx["name"] for idx in insp.get_indexes("simulation_observations")}

        names = await conn.run_sync(_list_indexes)

    expected = {
        "ix_simulation_observations_phase2_experiment_id",
        "ix_simulation_observations_paradigm",
        "ix_simulation_observations_formulation",
        "ix_simulation_observations_phase1_run_id",
        "ix_simulation_observations_memory_type",
        "ix_simulation_observations_created_at",
    }
    assert expected.issubset(names)


@pytest.mark.asyncio
async def test_simulation_observation_defaults(session):
    """SimulationObservation defaults: namespace='simulation', source_stage='tracker', confidence=0.80."""
    obs = SimulationObservation(
        content="agent foraged successfully",
        memory_type="semantic",
        importance=5.0,
        paradigm="hedonic",
    )
    session.add(obs)
    await session.commit()
    obs_id = obs.id

    session.expire_all()
    result = await session.execute(
        select(
            SimulationObservation.namespace,
            SimulationObservation.source_stage,
            SimulationObservation.confidence,
            SimulationObservation.created_at,
        ).where(SimulationObservation.id == obs_id)
    )
    row = result.one()
    assert row.namespace == "simulation"
    assert row.source_stage == "tracker"
    assert row.confidence == pytest.approx(0.80)
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_model_metadata_field_uses_metadata_column(session):
    """The metadata_ Python attr maps to the 'metadata' column with JSONB."""
    run = Run(problem_description="meta", s3_prefix="r/")
    session.add(run)
    await session.commit()
    run_id = run.id

    mod = Model(
        class_name="X",
        paradigm="p",
        formulation="f",
        run_id=run_id,
        s3_model_key="x",
        metadata_={"k": [1, 2, 3], "nested": {"a": True}},
    )
    session.add(mod)
    await session.commit()
    mod_id = mod.id

    session.expire_all()
    result = await session.execute(select(Model.metadata_).where(Model.id == mod_id))
    assert result.scalar_one() == {"k": [1, 2, 3], "nested": {"a": True}}


@pytest.mark.asyncio
async def test_uuid_primary_keys_generated(session):
    """All ORM models auto-generate UUIDs for the primary key."""
    run = Run(problem_description="uuid", s3_prefix="r/")
    exp = Experiment(description="exp uuid")
    session.add_all([run, exp])
    await session.commit()
    assert isinstance(run.id, uuid.UUID)
    assert isinstance(exp.id, uuid.UUID)


# ── Run.kind: defaults, allowed values, CHECK constraint (P3-003) ──


@pytest.mark.asyncio
async def test_run_kind_defaults_to_prod(session):
    """Inserting a Run without specifying kind yields kind='prod'."""
    run = Run(problem_description="kind default", s3_prefix="r/")
    session.add(run)
    await session.commit()
    run_id = run.id
    session.expire_all()
    result = await session.execute(select(Run.kind).where(Run.id == run_id))
    assert result.scalar_one() == "prod"


@pytest.mark.asyncio
async def test_run_kind_eval_allowed(session):
    run = Run(problem_description="kind eval", s3_prefix="r/", kind="eval")
    session.add(run)
    await session.commit()
    run_id = run.id
    session.expire_all()
    result = await session.execute(select(Run.kind).where(Run.id == run_id))
    assert result.scalar_one() == "eval"


@pytest.mark.asyncio
async def test_run_kind_check_constraint_rejects_unknown(session):
    """The runs_kind_check CHECK constraint rejects values outside {prod, eval}."""
    run = Run(problem_description="kind bogus", s3_prefix="r/", kind="staging")
    session.add(run)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_delete_run_cascades_to_dependents(session):
    """Deleting a run cascades to pipeline_memories, artifacts, node_run_observations."""
    run = Run(problem_description="cascade", s3_prefix="r/", kind="eval")
    session.add(run)
    await session.commit()
    run_id = run.id

    mem = Memory(
        content="cascaded",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run_id,
        importance=5.0,
        confidence=0.8,
    )
    art = Artifact(
        s3_key=f"runs/{run_id}/x.txt",
        artifact_type="report",
        size_bytes=10,
        content_type="text/plain",
        run_id=run_id,
    )
    obs = NodeRunObservation(label="Paradigm", key_value="rl", run_id=run_id)
    session.add_all([mem, art, obs])
    await session.commit()

    fetched_run = await session.get(Run, run_id)
    await session.delete(fetched_run)
    await session.commit()

    session.expire_all()
    assert (
        await session.execute(select(Memory).where(Memory.run_id == run_id))
    ).first() is None
    assert (
        await session.execute(select(Artifact).where(Artifact.run_id == run_id))
    ).first() is None
    assert (
        await session.execute(
            select(NodeRunObservation).where(NodeRunObservation.run_id == run_id)
        )
    ).first() is None
