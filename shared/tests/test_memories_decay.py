"""Tests for shared.memories.apply_time_decay.

Covers the consolidation-time confidence decay (0.95^periods over 30-day windows).
Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.memories import apply_time_decay, create_memory
from shared.models import Base, Memory
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


def _kwargs(**overrides) -> dict:
    base = dict(
        content="seed",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=5.0,
        confidence=0.8,
    )
    base.update(overrides)
    return base


async def _seed_memory(session, days_since_access: int | None, **kwargs):
    """Create a memory and optionally backdate last_accessed_at."""
    mem = await create_memory(session, **_kwargs(**kwargs))
    await session.commit()
    mem_id = mem.id
    if days_since_access is not None:
        backdate = datetime.now(UTC) - timedelta(days=days_since_access)
        await session.execute(
            update(Memory)
            .where(Memory.id == mem_id)
            .values(last_accessed_at=backdate.replace(tzinfo=None))
        )
        await session.commit()
    return mem_id


async def _get_confidence(session, mem_id) -> float:
    session.expire_all()
    result = await session.execute(
        select(Memory.confidence).where(Memory.id == mem_id)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_apply_decay_skips_recent(session):
    """Memories accessed <30 days ago are not decayed."""
    await _seed_memory(session, days_since_access=10, content="recent")

    decayed = await apply_time_decay(session)
    await session.commit()
    assert decayed == 0


@pytest.mark.asyncio
async def test_apply_decay_skips_reflections(session):
    """Memories of type 'reflection' are exempt from decay."""
    await _seed_memory(
        session,
        days_since_access=120,
        content="ref",
        memory_type="reflection",
    )

    decayed = await apply_time_decay(session)
    await session.commit()
    assert decayed == 0


@pytest.mark.asyncio
async def test_apply_decay_skips_invalidated(session):
    """Memories with valid_to set are skipped."""
    await _seed_memory(
        session,
        days_since_access=120,
        content="expired",
        valid_to=datetime(2020, 1, 1),
    )

    decayed = await apply_time_decay(session)
    assert decayed == 0


@pytest.mark.asyncio
async def test_apply_decay_one_period(session):
    """Memory accessed 30+ days ago decays once: confidence *= 0.95."""
    mem_id = await _seed_memory(
        session, days_since_access=35, content="30d", confidence=0.8,
    )

    decayed = await apply_time_decay(session)
    await session.commit()
    assert decayed == 1

    confidence = await _get_confidence(session, mem_id)
    assert confidence == pytest.approx(0.8 * 0.95)


@pytest.mark.asyncio
async def test_apply_decay_multiple_periods(session):
    """Memory accessed 90+ days ago decays 3 times: 0.95^3."""
    mem_id = await _seed_memory(
        session, days_since_access=95, content="90d", confidence=0.8,
    )

    decayed = await apply_time_decay(session)
    await session.commit()
    assert decayed == 1

    confidence = await _get_confidence(session, mem_id)
    assert confidence == pytest.approx(0.8 * (0.95**3))


@pytest.mark.asyncio
async def test_apply_decay_floors_at_0_1(session):
    """Confidence is clamped to floor 0.1 even after extreme decay."""
    mem_id = await _seed_memory(
        session, days_since_access=365 * 5, content="ancient", confidence=0.15,
    )

    await apply_time_decay(session)
    await session.commit()

    confidence = await _get_confidence(session, mem_id)
    assert confidence == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_apply_decay_skips_never_accessed(session):
    """Memories with last_accessed_at IS NULL are not selected."""
    await _seed_memory(session, days_since_access=None, content="untouched")

    decayed = await apply_time_decay(session)
    assert decayed == 0
