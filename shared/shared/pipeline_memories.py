"""Async helper functions for the ``pipeline_memories`` table.

Phase 1 lifecycle ops: insert, supersede, corroborate/contradict, decay,
prune, batched touch, time-travel queries. Phase 2 simulation observations
have their own helper in :mod:`shared.simulation_observations`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import PipelineMemory

_CONFIDENCE_CAP = 1.0
_CONFIDENCE_FLOOR = 0.1


async def update_memory_confidence(
    session: AsyncSession,
    memory_id: uuid.UUID,
    *,
    delta: float | None = None,
    set_to: float | None = None,
) -> float:
    """Apply a confidence change atomically, clamp, and return the new value.

    Exactly one of *delta* / *set_to* must be provided. Clamps the result to
    ``[_CONFIDENCE_FLOOR, _CONFIDENCE_CAP]``.
    """
    if (delta is None) == (set_to is None):
        raise ValueError("exactly one of delta / set_to must be provided")

    target: object = PipelineMemory.confidence + delta if delta is not None else set_to
    clamped = func.least(_CONFIDENCE_CAP, func.greatest(_CONFIDENCE_FLOOR, target))

    stmt = (
        update(PipelineMemory)
        .where(PipelineMemory.id == memory_id)
        .values(confidence=clamped)
        .returning(PipelineMemory.confidence)
    )
    result = await session.execute(stmt)
    new_confidence = result.scalar_one()
    await session.flush()
    return float(new_confidence)


async def create_memory(session: AsyncSession, **kwargs: object) -> PipelineMemory:
    """Create and persist a new PipelineMemory row."""
    memory = PipelineMemory(**kwargs)
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
) -> list[PipelineMemory]:
    """Query memories with optional filters."""
    stmt = select(PipelineMemory)
    if namespace is not None:
        stmt = stmt.where(PipelineMemory.namespace == namespace)
    if min_confidence is not None:
        stmt = stmt.where(PipelineMemory.confidence >= min_confidence)
    if valid_only:
        stmt = stmt.where(PipelineMemory.valid_to.is_(None))
    stmt = stmt.order_by(PipelineMemory.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def touch_memory(
    session: AsyncSession,
    memory_id: uuid.UUID | Iterable[uuid.UUID],
) -> int:
    """Bump access metadata for one or more memory rows.

    Accepts a single UUID or any iterable of UUIDs. Issues one batched UPDATE
    for `last_accessed_at` and `access_count`, then routes each id through
    `update_memory_confidence` for the +0.02 boost. Returns the number of ids
    targeted (0 when an empty iterable is passed — no SQL is sent).
    """
    if isinstance(memory_id, uuid.UUID):
        ids: list[uuid.UUID] = [memory_id]
    else:
        ids = list(memory_id)

    if not ids:
        return 0

    stmt = (
        update(PipelineMemory)
        .where(PipelineMemory.id.in_(ids))
        .values(
            last_accessed_at=func.now(),
            access_count=PipelineMemory.access_count + 1,
        )
    )
    await session.execute(stmt)
    for mid in ids:
        await update_memory_confidence(session, mid, delta=0.02)
    await session.flush()
    return len(ids)


async def supersede_memory(
    session: AsyncSession,
    old_id: uuid.UUID,
    new_content: str,
    **kwargs: object,
) -> PipelineMemory:
    """Mark an existing memory as superseded and create a replacement."""
    new_memory = PipelineMemory(content=new_content, **kwargs)
    session.add(new_memory)
    await session.flush()

    stmt = (
        update(PipelineMemory)
        .where(PipelineMemory.id == old_id)
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
    """Increment corroboration/contradiction counters and adjust confidence.

    Corroboration: +0.05, Contradiction: -0.10.
    Confidence is clamped to [0.1, 1.0] via `update_memory_confidence`.
    """
    values: dict[str, object] = {}
    delta = 0.0
    if corroborate:
        values["corroborations"] = PipelineMemory.corroborations + 1
        delta += 0.05
    if contradict:
        values["contradictions"] = PipelineMemory.contradictions + 1
        delta -= 0.10
    if not values:
        return
    stmt = update(PipelineMemory).where(PipelineMemory.id == memory_id).values(**values)
    await session.execute(stmt)
    if delta:
        await update_memory_confidence(session, memory_id, delta=delta)
    await session.flush()


_DECAY_RATE = 0.95
_DECAY_PERIOD_DAYS = 30


async def apply_time_decay(session: AsyncSession) -> int:
    """Apply time-based confidence decay during consolidation.

    For valid memories not accessed in >30 days (excluding reflections):
        periods = (now - last_accessed_at).days // 30
        confidence *= 0.95 ** periods
    Confidence is floored at 0.1.

    Returns the number of memories decayed.
    """
    now = datetime.now(UTC)
    # Strip tz for comparison against naive TIMESTAMP columns.
    cutoff_naive = (now - timedelta(days=_DECAY_PERIOD_DAYS)).replace(tzinfo=None)

    stmt = select(PipelineMemory).where(
        and_(
            PipelineMemory.valid_to.is_(None),
            PipelineMemory.memory_type != "reflection",
            PipelineMemory.last_accessed_at < cutoff_naive,
        ),
    )
    result = await session.execute(stmt)
    memories = result.scalars().all()

    count = 0
    for mem in memories:
        laa = mem.last_accessed_at
        if laa is None:
            continue
        if laa.tzinfo is None:
            laa = laa.replace(tzinfo=UTC)
        days_since = (now - laa).days
        periods = days_since // _DECAY_PERIOD_DAYS
        if periods <= 0:
            continue

        new_confidence = mem.confidence * _DECAY_RATE**periods
        await update_memory_confidence(session, mem.id, set_to=new_confidence)
        count += 1

    if count:
        await session.flush()
    return count


async def get_memories_at_time(
    session: AsyncSession,
    as_of: datetime,
    namespace: str | None = None,
) -> list[PipelineMemory]:
    """Return memories that were valid at *as_of*.

    Filters: valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of).
    Strips timezone info from *as_of* to match naive TIMESTAMP columns.
    """
    if as_of.tzinfo is not None:
        as_of = as_of.replace(tzinfo=None)
    stmt = select(PipelineMemory).where(
        PipelineMemory.valid_from <= as_of,
        or_(PipelineMemory.valid_to.is_(None), PipelineMemory.valid_to > as_of),
    )
    if namespace is not None:
        stmt = stmt.where(PipelineMemory.namespace == namespace)
    stmt = stmt.order_by(PipelineMemory.valid_from.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_memory_history(
    session: AsyncSession,
    content_like: str,
) -> list[PipelineMemory]:
    """Return a memory and all its superseded predecessors.

    Searches by LIKE pattern on content (e.g. "parameter value%") and
    returns all matching versions ordered by valid_from ascending.
    """
    stmt = (
        select(PipelineMemory)
        .where(PipelineMemory.content.like(content_like))
        .order_by(PipelineMemory.valid_from.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


_MAX_CHAIN_LENGTH = 1000


async def get_supersession_chain(
    session: AsyncSession,
    memory_id: uuid.UUID,
) -> list[PipelineMemory]:
    """Follow superseded_by pointers from *memory_id* to the current version.

    Returns the chain in chronological order (oldest first).
    Returns empty list if memory_id does not exist.
    Detects cycles and caps traversal at ``_MAX_CHAIN_LENGTH``.
    """
    chain: list[PipelineMemory] = []
    seen: set[uuid.UUID] = set()
    current_id: uuid.UUID | None = memory_id

    while current_id is not None and len(chain) < _MAX_CHAIN_LENGTH:
        if current_id in seen:
            break
        seen.add(current_id)
        result = await session.execute(
            select(PipelineMemory).where(PipelineMemory.id == current_id)
        )
        mem = result.scalar_one_or_none()
        if mem is None:
            break
        chain.append(mem)
        current_id = mem.superseded_by

    return chain
