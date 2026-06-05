"""P1-001 scaffold tests — verify public surface, flag-off behaviour, tool schema."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

from simlab.recall import (
    RETRIEVE_CONTEXT_TOOL,
    build_retriever_from_settings,
    retrieve_context,
)

from shared.services import Services
from shared.settings import Settings

_EMPTY = "## Retrieved Knowledge (0 results)\n\nNo results found."


def _make_services(*, kg=None, vectors=None, embeddings=None) -> Services:
    return Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=kg,
        vectors=vectors,
        embeddings=embeddings,
    )


# ── Public imports ──────────────────────────────────────────────────────


def test_public_imports():
    """AC1: public API is importable."""
    assert callable(retrieve_context)
    assert callable(build_retriever_from_settings)
    assert isinstance(RETRIEVE_CONTEXT_TOOL, dict)


# ── Flag OFF (default) ─────────────────────────────────────────────────


async def test_retrieve_context_flag_off_returns_empty():
    """AC2: with ENABLE_KNOWLEDGE_READ=False, returns 0-results immediately."""
    services = _make_services()
    with patch("simlab.recall.retrieve.load_settings", return_value=Settings()):
        result = await retrieve_context(services=services, query="test query")
    assert result == _EMPTY


async def test_retrieve_context_flag_off_never_calls_pablo():
    """AC2: with flag off, decisionlab is never imported/called."""
    services = _make_services()
    with (
        patch("simlab.recall.retrieve.load_settings", return_value=Settings()),
        patch.dict("sys.modules", {"decisionlab.knowledge.retrieval.tool": None}),
    ):
        result = await retrieve_context(services=services, query="anything")
    assert result == _EMPTY


# ── Infra missing ──────────────────────────────────────────────────────


async def test_retrieve_context_flag_on_but_no_infra():
    """With flag on but all infra None, returns empty without error."""
    services = _make_services()
    settings = Settings(ENABLE_KNOWLEDGE_READ=True)
    with patch("simlab.recall.retrieve.load_settings", return_value=settings):
        result = await retrieve_context(services=services, query="test")
    assert result == _EMPTY


# ── Exception handling ──────────────────────────────────────────────────


async def test_retrieve_context_exception_returns_empty(caplog):
    """AC4 (partial): any exception from Pablo's tool is caught."""
    services = _make_services(vectors=MagicMock())  # non-None so infra check passes
    settings = Settings(ENABLE_KNOWLEDGE_READ=True)

    with (
        patch("simlab.recall.retrieve.load_settings", return_value=settings),
        patch(
            "decisionlab.knowledge.retrieval.tool.create_retrieve_knowledge",
            side_effect=RuntimeError("boom"),
        ),
        caplog.at_level("ERROR", logger="simlab.recall.retrieve"),
    ):
        result = await retrieve_context(services=services, query="test")

    assert result == _EMPTY
    assert any("retrieve_context failed" in r.message for r in caplog.records)


async def test_retrieve_context_timeout_returns_empty(caplog, monkeypatch):
    """A slow retrieval backend must not block agent turns indefinitely."""

    async def slow_handler(_params):
        await asyncio.sleep(0.05)
        return "late"

    services = _make_services(vectors=MagicMock())
    settings = Settings(ENABLE_KNOWLEDGE_READ=True)

    monkeypatch.setattr(
        "simlab.recall.retrieve._RETRIEVE_CONTEXT_TIMEOUT_SECONDS", 0.01
    )
    with (
        patch("simlab.recall.retrieve.load_settings", return_value=settings),
        patch(
            "decisionlab.knowledge.retrieval.tool.create_retrieve_knowledge",
            return_value=slow_handler,
        ),
        caplog.at_level("WARNING", logger="simlab.recall.retrieve"),
    ):
        result = await retrieve_context(services=services, query="test")

    assert result == _EMPTY
    assert any("retrieve_context timed out" in r.message for r in caplog.records)


# ── Tool schema ─────────────────────────────────────────────────────────


def test_tool_schema_is_json_serializable():
    """AC3: schema round-trips through JSON."""
    dumped = json.dumps(RETRIEVE_CONTEXT_TOOL)
    loaded = json.loads(dumped)
    assert loaded == RETRIEVE_CONTEXT_TOOL


def test_tool_schema_has_required_anthropic_keys():
    """AC3: schema has name, description, input_schema with correct structure."""
    assert RETRIEVE_CONTEXT_TOOL["name"] == "retrieve_context"
    assert isinstance(RETRIEVE_CONTEXT_TOOL["description"], str)
    schema = RETRIEVE_CONTEXT_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert "query" in schema["required"]


# ── Factory ─────────────────────────────────────────────────────────────


async def test_build_retriever_returns_none_flag_off():
    """AC4: factory returns None when flag is off."""
    services = _make_services()
    result = await build_retriever_from_settings(services, Settings())
    assert result is None


async def test_build_retriever_returns_none_no_infra():
    """AC4: factory returns None when flag on but infra missing."""
    services = _make_services()
    settings = Settings(ENABLE_KNOWLEDGE_READ=True)
    result = await build_retriever_from_settings(services, settings)
    assert result is None


async def test_build_retriever_returns_callable_when_ready():
    """AC4: factory returns callable when flag on and infra available."""
    services = _make_services(vectors=MagicMock())
    settings = Settings(ENABLE_KNOWLEDGE_READ=True)
    result = await build_retriever_from_settings(services, settings)
    assert callable(result)
