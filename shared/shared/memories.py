"""Async helper functions for the memories table."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Memory


async def create_memory(session: AsyncSession, **kwargs: object) -> Memory:
    """Create and persist a new Memory row."""
    memory = Memory(**kwargs)
    session.add(memory)
    await session.flush()
    return memory


async def get_memories(
    session: AsyncSession,
    *,
    namespace: str | None = None,
    min_confidence: float | None = None,
    valid_only: bool = True,
    limit: int = 50,
) -> list[Memory]:
    """Query memories with optional filters."""
    stmt = select(Memory)
    if namespace is not None:
        stmt = stmt.where(Memory.namespace == namespace)
    if min_confidence is not None:
        stmt = stmt.where(Memory.confidence >= min_confidence)
    if valid_only:
        stmt = stmt.where(Memory.valid_to.is_(None))
    stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def touch_memory(session: AsyncSession, memory_id: uuid.UUID) -> None:
    """Update last_accessed_at and increment access_count."""
    stmt = (
        update(Memory)
        .where(Memory.id == memory_id)
        .values(
            last_accessed_at=func.now(),
            access_count=Memory.access_count + 1,
        )
    )
    await session.execute(stmt)
    await session.flush()


async def supersede_memory(
    session: AsyncSession,
    old_id: uuid.UUID,
    new_content: str,
    **kwargs: object,
) -> Memory:
    """Mark an existing memory as superseded and create a replacement."""
    new_memory = Memory(content=new_content, **kwargs)
    session.add(new_memory)
    await session.flush()

    stmt = (
        update(Memory)
        .where(Memory.id == old_id)
        .values(valid_to=func.now(), superseded_by=new_memory.id)
    )
    await session.execute(stmt)
    await session.flush()

    return new_memory


async def update_confidence(
    session: AsyncSession,
    memory_id: uuid.UUID,
    *,
    corroborate: bool = False,
    contradict: bool = False,
) -> None:
    """Increment corroboration/contradiction counters and adjust confidence."""
    values: dict[str, object] = {}
    delta = 0.0
    if corroborate:
        values["corroborations"] = Memory.corroborations + 1
        delta += 0.05
    if contradict:
        values["contradictions"] = Memory.contradictions + 1
        delta -= 0.05
    if not values:
        return
    if delta:
        values["confidence"] = Memory.confidence + delta
    stmt = update(Memory).where(Memory.id == memory_id).values(**values)
    await session.execute(stmt)
    await session.flush()
