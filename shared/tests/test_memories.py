"""Tests for the Memory model and helper functions.

Covers all P1-002 acceptance criteria (AC1–AC6).
Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.memories import (
    create_memory,
    get_memories,
    supersede_memory,
    touch_memory,
    update_confidence,
)
from shared.models import Base, Memory, Run
from shared.settings import load_settings

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


def _memory_kwargs(**overrides: object) -> dict:
    """Default kwargs for creating a Memory."""
    defaults = dict(
        content="Dopamine mediates wanting, not liking",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=7.0,
        confidence=0.8,
    )
    defaults.update(overrides)
    return defaults


# ── AC1: create_all creates the memories table alongside existing tables ──


@pytest.mark.asyncio
async def test_ac1_create_all_creates_memories_table(engine):
    """AC1: create_all() creates memories table without error."""
    async with engine.begin() as conn:
        # Verify memory table exists by querying it
        result = await conn.execute(select(Memory))
        rows = result.all()
        assert rows == []


# ── AC2: CRUD with all required fields, query by namespace ──


@pytest.mark.asyncio
async def test_ac2_create_and_query_by_namespace(session):
    """AC2: Create a Memory, persist it, query it back by namespace."""
    mem = await create_memory(session, **_memory_kwargs())
    await session.commit()

    assert mem.id is not None
    assert isinstance(mem.id, uuid.UUID)

    results = await get_memories(session, namespace="paradigm")
    assert len(results) == 1
    assert results[0].content == "Dopamine mediates wanting, not liking"
    assert results[0].namespace == "paradigm"
    assert results[0].memory_type == "semantic"


@pytest.mark.asyncio
async def test_ac2_query_filters_by_namespace(session):
    """AC2: get_memories filters correctly — only matching namespace returned."""
    await create_memory(session, **_memory_kwargs(namespace="paradigm"))
    await create_memory(
        session,
        **_memory_kwargs(namespace="formulation", content="ODE pattern"),
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
async def test_ac3_get_memories_valid_only(session):
    """AC3: get_memories(valid_only=True) excludes expired memories."""
    # Valid memory (valid_to is None)
    await create_memory(session, **_memory_kwargs(content="still valid"))
    # Expired memory
    await create_memory(
        session,
        **_memory_kwargs(
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
async def test_ac4_supersede_memory(session):
    """AC4: supersede_memory sets valid_to and superseded_by, creates new."""
    old = await create_memory(session, **_memory_kwargs(content="old fact"))
    await session.commit()
    old_id = old.id

    kwargs = _memory_kwargs()
    kwargs.pop("content")
    new = await supersede_memory(
        session, old_id=old_id, new_content="updated fact", **kwargs
    )
    new_id = new.id
    await session.commit()

    # Re-query both from DB
    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == old_id))
    old_refreshed = result.scalar_one()
    result = await session.execute(select(Memory).where(Memory.id == new_id))
    new_refreshed = result.scalar_one()

    assert old_refreshed.valid_to is not None
    assert old_refreshed.superseded_by == new_id
    assert new_refreshed.content == "updated fact"

    # valid_only should only return the new one
    valid = await get_memories(session, valid_only=True)
    assert len(valid) == 1
    assert valid[0].id == new_id


# ── AC5: update_confidence ──


@pytest.mark.asyncio
async def test_ac5_corroborate_increases_confidence(session):
    """AC5: update_confidence(corroborate=True) increments and increases."""
    mem = await create_memory(session, **_memory_kwargs(confidence=0.5))
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
async def test_ac5_contradict_decreases_confidence(session):
    """AC5: update_confidence(contradict=True) increments and decreases."""
    mem = await create_memory(session, **_memory_kwargs(confidence=0.8))
    await session.commit()
    mem_id = mem.id

    await update_confidence(session, mem_id, contradict=True)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated = result.scalar_one()

    assert updated.contradictions == 1
    assert updated.confidence == pytest.approx(0.75)


# ── AC6: touch_memory ──


@pytest.mark.asyncio
async def test_ac6_touch_memory(session):
    """AC6: touch_memory updates last_accessed_at and increments access_count."""
    mem = await create_memory(session, **_memory_kwargs())
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

    # Touch again
    await touch_memory(session, mem_id)
    await session.commit()

    session.expire_all()
    result = await session.execute(select(Memory).where(Memory.id == mem_id))
    updated2 = result.scalar_one()
    assert updated2.access_count == 2


# ── Additional: min_confidence filter ──


@pytest.mark.asyncio
async def test_get_memories_min_confidence(session):
    """get_memories with min_confidence filters low-confidence memories."""
    await create_memory(session, **_memory_kwargs(confidence=0.3))
    await create_memory(session, **_memory_kwargs(confidence=0.9, content="high conf"))
    await session.commit()

    results = await get_memories(session, min_confidence=0.5)
    assert len(results) == 1
    assert results[0].confidence == pytest.approx(0.9)


# ── Additional: Memory with run_id FK ──


@pytest.mark.asyncio
async def test_memory_with_run_fk(session):
    """Memory can link to a Run via run_id."""
    run = Run(
        problem_description="Test run",
        s3_prefix="runs/test/",
    )
    session.add(run)
    await session.commit()

    mem = await create_memory(session, **_memory_kwargs(run_id=run.id))
    await session.commit()

    assert mem.run_id == run.id
