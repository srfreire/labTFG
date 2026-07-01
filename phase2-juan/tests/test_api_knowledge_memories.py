"""Tests for /api/knowledge/memories endpoint (knowledge P7-002)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import simlab.api as api_module
from fastapi import HTTPException
from simlab.api import knowledge_memories


def _stub_memory(
    *,
    id: uuid.UUID | None = None,
    content: str = "fact",
    namespace: str = "paradigm",
    run_id: uuid.UUID | None = None,
    memory_type: str = "semantic",
    source_stage: str = "researcher",
    created_at: datetime | None = None,
) -> MagicMock:
    """Build a fake PipelineMemory row."""
    m = MagicMock()
    m.id = id or uuid.uuid4()
    m.content = content
    m.namespace = namespace
    m.run_id = run_id or uuid.uuid4()
    m.memory_type = memory_type
    m.source_stage = source_stage
    m.created_at = created_at or datetime.now(timezone.utc)
    return m


def _stub_db(items: list, total: int) -> MagicMock:
    """Build a fake DatabaseService where session.execute returns canned rows.

    First call returns the items query (scalars().all() → items).
    Second call returns the count (scalar_one() → total).
    """
    items_result = MagicMock()
    items_result.scalars = MagicMock(return_value=MagicMock(all=lambda: items))

    count_result = MagicMock()
    count_result.scalar_one = MagicMock(return_value=total)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=[items_result, count_result])

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.get_session = MagicMock(return_value=cm)
    return db


def _set_services(monkeypatch, *, db=None):
    services = MagicMock()
    services.db = db
    monkeypatch.setattr(api_module, "_services", services)


async def test_returns_paginated_items(monkeypatch):
    rows = [_stub_memory(namespace="paradigm"), _stub_memory(namespace="meta")]
    _set_services(monkeypatch, db=_stub_db(rows, total=2))

    body = await knowledge_memories()

    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert isinstance(body["items"][0]["id"], str)
    assert isinstance(body["items"][0]["run_id"], str)


async def test_namespace_filter_passes_through(monkeypatch):
    rows = [_stub_memory(namespace="paradigm")]
    _set_services(monkeypatch, db=_stub_db(rows, total=1))

    body = await knowledge_memories(namespace="paradigm")

    assert body["total"] == 1
    assert body["items"][0]["namespace"] == "paradigm"


async def test_invalid_run_id_returns_400(monkeypatch):
    _set_services(monkeypatch, db=_stub_db([], total=0))

    with pytest.raises(HTTPException) as exc:
        await knowledge_memories(run_id="not-a-uuid")

    assert exc.value.status_code == 400


async def test_invalid_since_returns_400(monkeypatch):
    _set_services(monkeypatch, db=_stub_db([], total=0))

    with pytest.raises(HTTPException) as exc:
        await knowledge_memories(since="yesterday")

    assert exc.value.status_code == 400


async def test_valid_since_accepts_z_suffix(monkeypatch):
    rows = [_stub_memory()]
    _set_services(monkeypatch, db=_stub_db(rows, total=1))

    body = await knowledge_memories(since="2026-01-01T00:00:00Z")

    assert body["total"] == 1


async def test_page_size_capped_to_max(monkeypatch):
    _set_services(monkeypatch, db=_stub_db([], total=0))

    body = await knowledge_memories(page_size=500)

    assert body["page_size"] == 200


async def test_page_size_floor(monkeypatch):
    _set_services(monkeypatch, db=_stub_db([], total=0))

    body = await knowledge_memories(page_size=0)

    assert body["page_size"] == 1


async def test_page_floor(monkeypatch):
    _set_services(monkeypatch, db=_stub_db([], total=0))

    body = await knowledge_memories(page=-3)

    assert body["page"] == 1


async def test_returns_503_when_db_is_none(monkeypatch):
    _set_services(monkeypatch, db=None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_memories()

    assert exc.value.status_code == 503


async def test_returns_503_when_services_is_none(monkeypatch):
    monkeypatch.setattr(api_module, "_services", None)

    with pytest.raises(HTTPException) as exc:
        await knowledge_memories()

    assert exc.value.status_code == 503


async def test_returns_503_when_query_raises(monkeypatch):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    db = MagicMock()
    db.get_session = MagicMock(return_value=cm)
    _set_services(monkeypatch, db=db)

    with pytest.raises(HTTPException) as exc:
        await knowledge_memories()

    assert exc.value.status_code == 503
