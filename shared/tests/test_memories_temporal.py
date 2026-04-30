"""Tests for temporal memory query functions (P5-004).

Covers get_memories_at_time, get_memory_history, get_supersession_chain.
Requires docker-compose Postgres running on localhost:5432.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.memories import (
    create_memory,
    get_memories_at_time,
    get_memory_history,
    get_supersession_chain,
    supersede_memory,
)
from shared.models import Base
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


def _mem_kwargs(**overrides: object) -> dict:
    defaults = dict(
        content="Ghrelin stimulates appetite",
        namespace="paradigm",
        memory_type="semantic",
        source_stage="researcher",
        importance=7.0,
        confidence=0.8,
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# AC2: get_memories_at_time returns knowledge valid at a specific point
# ---------------------------------------------------------------------------


class TestGetMemoriesAtTime:
    @pytest.mark.asyncio
    async def test_returns_memories_valid_at_given_time(self, session):
        """Memories valid at as_of are returned; future and expired are excluded."""
        now = datetime.now()
        past = now - timedelta(days=10)
        future = now + timedelta(days=10)

        # Memory valid from past, no expiry (currently valid)
        await create_memory(
            session,
            **_mem_kwargs(
                content="valid-at-past",
                valid_from=past,
            ),
        )
        # Memory valid from future (not yet valid at past)
        await create_memory(
            session,
            **_mem_kwargs(
                content="future-only",
                valid_from=future,
            ),
        )
        # Memory expired before query time
        await create_memory(
            session,
            **_mem_kwargs(
                content="expired",
                valid_from=past - timedelta(days=20),
                valid_to=past - timedelta(days=5),
            ),
        )
        await session.commit()

        # Query at "past" — should only see the first one
        results = await get_memories_at_time(session, as_of=past)
        contents = [m.content for m in results]
        assert "valid-at-past" in contents
        assert "future-only" not in contents
        assert "expired" not in contents

    @pytest.mark.asyncio
    async def test_includes_memories_with_null_valid_to(self, session):
        """Memories with valid_to=NULL are considered currently valid."""
        now = datetime.now()
        past = now - timedelta(days=5)

        await create_memory(
            session,
            **_mem_kwargs(
                content="no-expiry",
                valid_from=past,
            ),
        )
        await session.commit()

        results = await get_memories_at_time(session, as_of=now)
        assert len(results) == 1
        assert results[0].content == "no-expiry"

    @pytest.mark.asyncio
    async def test_filters_by_namespace(self, session):
        """get_memories_at_time respects optional namespace filter."""
        now = datetime.now()
        past = now - timedelta(days=5)

        await create_memory(
            session,
            **_mem_kwargs(
                content="paradigm-fact",
                namespace="paradigm",
                valid_from=past,
            ),
        )
        await create_memory(
            session,
            **_mem_kwargs(
                content="model-fact",
                namespace="model",
                valid_from=past,
            ),
        )
        await session.commit()

        results = await get_memories_at_time(session, as_of=now, namespace="paradigm")
        assert len(results) == 1
        assert results[0].content == "paradigm-fact"


# ---------------------------------------------------------------------------
# AC1: get_memory_history returns all versions ordered chronologically
# ---------------------------------------------------------------------------


class TestGetMemoryHistory:
    @pytest.mark.asyncio
    async def test_returns_supersession_chain_for_content(self, session):
        """After 3 versions of a fact, get_memory_history returns all 3."""
        # Create v1
        v1 = await create_memory(
            session,
            **_mem_kwargs(
                content="parameter value is 50",
            ),
        )
        await session.commit()

        # Supersede v1 → v2
        kwargs = _mem_kwargs()
        kwargs.pop("content")
        v2 = await supersede_memory(session, v1.id, "parameter value is 70", **kwargs)
        await session.commit()

        # Supersede v2 → v3
        await supersede_memory(session, v2.id, "parameter value is 65", **kwargs)
        await session.commit()

        # Search for the full history of "parameter value"
        results = await get_memory_history(session, content_like="parameter value%")

        assert len(results) == 3
        # Ordered by valid_from ascending
        assert results[0].content == "parameter value is 50"
        assert results[-1].content == "parameter value is 65"

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_matches(self, session):
        """get_memory_history returns empty list when no content matches."""
        results = await get_memory_history(session, content_like="nonexistent%")
        assert results == []


# ---------------------------------------------------------------------------
# AC3: get_supersession_chain traverses forward to current version
# ---------------------------------------------------------------------------


class TestGetSupersessionChain:
    @pytest.mark.asyncio
    async def test_chain_from_original_to_current(self, session):
        """From the original memory, follows superseded_by to current version."""
        v1 = await create_memory(session, **_mem_kwargs(content="v1"))
        await session.commit()

        kwargs = _mem_kwargs()
        kwargs.pop("content")
        v2 = await supersede_memory(session, v1.id, "v2", **kwargs)
        await session.commit()
        v3 = await supersede_memory(session, v2.id, "v3", **kwargs)
        await session.commit()

        chain = await get_supersession_chain(session, v1.id)

        assert len(chain) == 3
        assert chain[0].id == v1.id
        assert chain[1].id == v2.id
        assert chain[2].id == v3.id

    @pytest.mark.asyncio
    async def test_single_memory_no_successors(self, session):
        """A memory with no superseded_by returns a chain of length 1."""
        mem = await create_memory(session, **_mem_kwargs(content="standalone"))
        await session.commit()

        chain = await get_supersession_chain(session, mem.id)
        assert len(chain) == 1
        assert chain[0].id == mem.id

    @pytest.mark.asyncio
    async def test_chain_from_middle(self, session):
        """Starting from a middle memory still reaches the current version."""
        v1 = await create_memory(session, **_mem_kwargs(content="v1"))
        await session.commit()

        kwargs = _mem_kwargs()
        kwargs.pop("content")
        v2 = await supersede_memory(session, v1.id, "v2", **kwargs)
        await session.commit()
        v3 = await supersede_memory(session, v2.id, "v3", **kwargs)
        await session.commit()

        chain = await get_supersession_chain(session, v2.id)

        assert len(chain) == 2
        assert chain[0].id == v2.id
        assert chain[1].id == v3.id

    @pytest.mark.asyncio
    async def test_nonexistent_memory_returns_empty(self, session):
        """Passing a non-existent memory_id returns empty chain."""
        chain = await get_supersession_chain(session, uuid.uuid4())
        assert chain == []
