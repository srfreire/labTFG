"""Tests for the PipelineMemory model and helper functions.

Covers all P1-002 acceptance criteria (AC1–AC6).
Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.models import Base, Run
from shared.models import PipelineMemory as Memory
from shared.pipeline_memories import (
    create_memory,
    create_memory_once,
    get_memories,
    memory_content_hash,
    supersede_memory,
    touch_memory,
    update_confidence,
    update_memory_confidence,
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


async def _make_run(session) -> uuid.UUID:
    run = Run(problem_description="memory tests", s3_prefix="r/")
    session.add(run)
    await session.commit()
    return run.id


@pytest_asyncio.fixture
async def run_id(session) -> uuid.UUID:
    """Insert a Run row and return its id — pipeline_memories.run_id is NOT NULL."""
    return await _make_run(session)


def _memory_kwargs(run_id: uuid.UUID, **overrides: object) -> dict:
    """Default kwargs for creating a PipelineMemory.

    ``run_id`` is required because ``pipeline_memories.run_id`` is NOT NULL
    after the P4-003 split.
    """
    defaults = dict(
        content="Dopamine mediates wanting, not liking",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        run_id=run_id,
        importance=7.0,
        confidence=0.8,
    )
    defaults.update(overrides)
    return defaults


# ── AC1: create_all creates the pipeline_memories table alongside existing tables ──


@pytest.mark.asyncio
async def test_ac1_create_all_creates_memories_table(engine):
    """AC1: create_all() creates pipeline_memories without error."""
    async with engine.begin() as conn:
        result = await conn.execute(select(Memory))
        rows = result.all()
        assert rows == []


# ── AC2: CRUD with all required fields, query by namespace ──


@pytest.mark.asyncio
async def test_ac2_create_and_query_by_namespace(session, run_id):
    """AC2: Create a Memory, persist it, query it back by namespace."""
    mem = await create_memory(session, **_memory_kwargs(run_id))
    await session.commit()

    assert mem.id is not None
    assert isinstance(mem.id, uuid.UUID)
    assert mem.content_hash == memory_content_hash(
        "Dopamine mediates wanting, not liking"
    )

    results = await get_memories(session, namespace="paradigm")
    assert len(results) == 1
    assert results[0].content == "Dopamine mediates wanting, not liking"
    assert results[0].namespace == "paradigm"
    assert results[0].memory_type == "semantic"


@pytest.mark.asyncio
async def test_ac2_query_filters_by_namespace(session, run_id):
    """AC2: get_memories filters correctly — only matching namespace returned."""
    await create_memory(session, **_memory_kwargs(run_id, namespace="paradigm"))
    await create_memory(
        session,
        **_memory_kwargs(run_id, namespace="formulation", content="ODE pattern"),
    )
    await session.commit()

    paradigm_results = await get_memories(session, namespace="paradigm")
    assert len(paradigm_results) == 1
    assert paradigm_results[0].namespace == "paradigm"

    formulation_results = await get_memories(session, namespace="formulation")
    assert len(formulation_results) == 1
    assert formulation_results[0].namespace == "formulation"


# ── AC3: valid_only excludes memories with non-null valid_to ──


@pytest.mark.asyncio
async def test_ac3_get_memories_valid_only(session, run_id):
    """AC3: get_memories(valid_only=True) excludes expired memories."""
    await create_memory(session, **_memory_kwargs(run_id, content="still valid"))
    await create_memory(
        session,
        **_memory_kwargs(
            run_id,
            content="expired",
            valid_to=datetime(2020, 1, 1),
        ),
    )
    await session.commit()

    valid = await get_memories(session, valid_only=True)
    assert len(valid) == 1
    assert valid[0].content == "still valid"

    all_memories = await get_memories(session, valid_only=False)
    assert len(all_memories) == 2


# ── AC4: supersede_memory ──


@pytest.mark.asyncio
async def test_ac4_supersede_memory(session, run_id):
    """AC4: supersede_memory sets valid_to and superseded_by, creates new."""
    old = await create_memory(session, **_memory_kwargs(run_id, content="old fact"))
    await session.commit()
    old_id = old.id

    kwargs = _memory_kwargs(run_id)
    kwargs.pop("content")
    new = await supersede_memory(
        session, old_id=old_id, new_content="updated fact", **kwargs
    )
    new_id = new.id
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == old_id))
    old_refreshed = result.scalar_one()
    result = await session.execute(select(Memory).where(Memory.id == new_id))
    new_refreshed = result.scalar_one()

    assert old_refreshed.valid_to is not None
    assert old_refreshed.superseded_by == new_id
    assert new_refreshed.content == "updated fact"

    valid = await get_memories(session, valid_only=True)
    assert len(valid) == 1
    assert valid[0].id == new_id


# ── AC5: update_confidence ──


@pytest.mark.asyncio
async def test_ac5_corroborate_increases_confidence(session, run_id):
    """AC5: update_confidence(corroborate=True) increments and increases."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.5))
    await session.commit()
    mem_id = mem.id

    await update_confidence(session, mem_id, corroborate=True)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated = result.scalar_one()

    assert updated.corroborations == 1
    assert updated.confidence == pytest.approx(0.55)


@pytest.mark.asyncio
async def test_ac5_contradict_decreases_confidence(session, run_id):
    """AC5: update_confidence(contradict=True) increments and decreases."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.8))
    await session.commit()
    mem_id = mem.id

    await update_confidence(session, mem_id, contradict=True)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated = result.scalar_one()

    assert updated.contradictions == 1
    assert updated.confidence == pytest.approx(0.70)


# ── AC6: touch_memory ──


@pytest.mark.asyncio
async def test_ac6_touch_memory(session, run_id):
    """AC6: touch_memory updates last_accessed_at and increments access_count."""
    mem = await create_memory(session, **_memory_kwargs(run_id))
    await session.commit()
    mem_id = mem.id
    assert mem.last_accessed_at is None
    assert mem.access_count == 0

    await touch_memory(session, mem_id)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated = result.scalar_one()

    assert updated.last_accessed_at is not None
    assert updated.access_count == 1

    await touch_memory(session, mem_id)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated2 = result.scalar_one()
    assert updated2.access_count == 2


# ── P2-003 AC5: batched touch_memory ──


@pytest.mark.asyncio
async def test_touch_memory_batch_updates_each_id(session, run_id):
    """P2-003 AC5: passing a list of ids updates access_count, last_accessed_at,
    and confidence (capped at 1.0) for every row in one round-trip."""
    mem_a = await create_memory(
        session, **_memory_kwargs(run_id, content="a", confidence=0.5)
    )
    mem_b = await create_memory(
        session, **_memory_kwargs(run_id, content="b", confidence=0.99)
    )
    mem_c = await create_memory(
        session, **_memory_kwargs(run_id, content="c", confidence=1.0)
    )
    await session.commit()

    ids = [mem_a.id, mem_b.id, mem_c.id]
    touched = await touch_memory(session, ids)
    await session.commit()
    assert touched == 3

    session.expire_all()
    rows = (
        (await session.execute(select(Memory).where(Memory.id.in_(ids))))
        .scalars()
        .all()
    )
    by_id = {m.id: m for m in rows}

    for mid in ids:
        assert by_id[mid].access_count == 1
        assert by_id[mid].last_accessed_at is not None

    assert by_id[mem_a.id].confidence == pytest.approx(0.52)
    assert by_id[mem_b.id].confidence == pytest.approx(1.0)  # clamped
    assert by_id[mem_c.id].confidence == pytest.approx(1.0)  # already at cap


@pytest.mark.asyncio
async def test_touch_memory_empty_list_is_noop(session):
    """Passing [] returns 0 and issues no SQL — no-op."""
    touched = await touch_memory(session, [])
    assert touched == 0


@pytest.mark.asyncio
async def test_touch_memory_ignores_missing_and_expired_ids(session, run_id):
    """Only live existing memories are touched/count boosted."""
    live = await create_memory(session, **_memory_kwargs(run_id, content="live"))
    expired = await create_memory(
        session,
        **_memory_kwargs(
            run_id,
            content="expired",
            valid_to=datetime(2020, 1, 1),
        ),
    )
    missing = uuid.uuid4()
    await session.commit()
    live_id = live.id
    expired_id = expired.id

    touched = await touch_memory(session, [live_id, expired_id, missing])
    await session.commit()

    assert touched == 1
    session.expire_all()
    rows = (
        await session.execute(
            select(Memory).where(Memory.id.in_([live_id, expired_id]))
        )
    ).scalars()
    by_id = {row.id: row for row in rows}
    assert by_id[live_id].access_count == 1
    assert by_id[expired_id].access_count == 0


@pytest.mark.asyncio
async def test_create_memory_once_reuses_same_live_fact(session, run_id):
    """Same run/stage/ns/type/content hash returns the existing live row."""
    kwargs = _memory_kwargs(run_id, content="  Same   Fact ")
    first, created_first = await create_memory_once(session, **kwargs)
    second, created_second = await create_memory_once(
        session,
        **_memory_kwargs(run_id, content="same fact"),
    )
    await session.commit()

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    rows = (
        await session.execute(select(Memory).where(Memory.run_id == run_id))
    ).scalars()
    assert len(list(rows)) == 1


# ── Additional: min_confidence filter ──


@pytest.mark.asyncio
async def test_get_memories_min_confidence(session, run_id):
    """get_memories with min_confidence filters low-confidence memories."""
    await create_memory(session, **_memory_kwargs(run_id, confidence=0.3))
    await create_memory(
        session, **_memory_kwargs(run_id, confidence=0.9, content="high conf")
    )
    await session.commit()

    results = await get_memories(session, min_confidence=0.5)
    assert len(results) == 1
    assert results[0].confidence == pytest.approx(0.9)


# ── P3-001: update_memory_confidence helper ──


@pytest.mark.asyncio
async def test_update_memory_confidence_delta_positive(session, run_id):
    """+delta increases confidence and returns the new value."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.5))
    await session.commit()

    new = await update_memory_confidence(session, mem.id, delta=0.05)
    await session.commit()
    assert new == pytest.approx(0.55)


@pytest.mark.asyncio
async def test_update_memory_confidence_delta_negative(session, run_id):
    """−delta decreases confidence and returns the new value."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.8))
    await session.commit()

    new = await update_memory_confidence(session, mem.id, delta=-0.10)
    await session.commit()
    assert new == pytest.approx(0.70)


@pytest.mark.asyncio
async def test_update_memory_confidence_clamps_upper(session, run_id):
    """+delta past 1.0 clamps at the cap."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.99))
    await session.commit()

    new = await update_memory_confidence(session, mem.id, delta=0.5)
    await session.commit()
    assert new == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_update_memory_confidence_clamps_lower(session, run_id):
    """−delta past 0.1 clamps at the floor."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.15))
    await session.commit()

    new = await update_memory_confidence(session, mem.id, delta=-0.5)
    await session.commit()
    assert new == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_update_memory_confidence_set_to(session, run_id):
    """set_to writes the value directly."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.5))
    await session.commit()

    new = await update_memory_confidence(session, mem.id, set_to=0.42)
    await session.commit()
    assert new == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_update_memory_confidence_set_to_out_of_range(session, run_id):
    """set_to outside [0.1, 1.0] is clamped on both ends."""
    mem = await create_memory(session, **_memory_kwargs(run_id, confidence=0.5))
    await session.commit()

    new_high = await update_memory_confidence(session, mem.id, set_to=2.0)
    await session.commit()
    assert new_high == pytest.approx(1.0)

    new_low = await update_memory_confidence(session, mem.id, set_to=0.0)
    await session.commit()
    assert new_low == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_update_memory_confidence_requires_exactly_one(session, run_id):
    """Passing both or neither delta/set_to raises ValueError."""
    mem = await create_memory(session, **_memory_kwargs(run_id))
    await session.commit()

    with pytest.raises(ValueError):
        await update_memory_confidence(session, mem.id)
    with pytest.raises(ValueError):
        await update_memory_confidence(session, mem.id, delta=0.05, set_to=0.5)


@pytest.mark.asyncio
async def test_update_memory_confidence_concurrent_corroborations(engine):
    """Concurrent corroborations on the same id converge to the right total."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as setup:
        run_id_local = await _make_run(setup)
        mem = await create_memory(setup, **_memory_kwargs(run_id_local, confidence=0.5))
        await setup.commit()
        mem_id = mem.id

    async def bump_one() -> None:
        async with factory() as sess:
            await update_memory_confidence(sess, mem_id, delta=0.05)
            await sess.commit()

    # 5 concurrent +0.05 bumps → 0.5 + 5*0.05 = 0.75
    await asyncio.gather(*(bump_one() for _ in range(5)))

    async with factory() as check:
        result = await check.execute(
            select(Memory.confidence).where(Memory.id == mem_id)
        )
        final = result.scalar_one()
    assert final == pytest.approx(0.75)


# ── Additional: PipelineMemory with run_id FK ──


@pytest.mark.asyncio
async def test_memory_with_run_fk(session):
    """PipelineMemory carries its run_id FK round-trip."""
    run = Run(
        problem_description="Test run",
        s3_prefix="runs/test/",
    )
    session.add(run)
    await session.commit()

    mem = await create_memory(session, **_memory_kwargs(run.id))
    await session.commit()

    assert mem.run_id == run.id
