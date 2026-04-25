"""P1-004 R1 — deeper wrapper unit tests for retrieve_context.

Complements test_scaffold.py with tests that exercise the flag-ON path
with a mocked ``create_retrieve_knowledge`` handler, verify parameter
propagation (namespace, as_of, stage, run_id), and confirm the handler
output is returned verbatim.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import shared
from shared.settings import Settings
from simlab.recall.retrieve import _EMPTY_RESULT, retrieve_context

_FLAG_ON = Settings(ENABLE_KNOWLEDGE_READ=True)
_FACTORY_PATH = "decisionlab.knowledge.retrieval.tool.create_retrieve_knowledge"
_SETTINGS_PATH = "simlab.recall.retrieve.load_settings"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_shared_singletons():
    originals = (shared.kg, shared.vectors, shared.embeddings)
    shared.kg = None
    shared.vectors = None
    shared.embeddings = None
    yield
    shared.kg, shared.vectors, shared.embeddings = originals


# ---------------------------------------------------------------------------
# Flag ON + mocked handler — happy path
# ---------------------------------------------------------------------------


async def test_flag_on_calls_create_retrieve_knowledge_with_correct_args():
    """With flag on and infra mocked, the handler factory is called correctly."""
    shared.vectors = MagicMock()
    shared.embeddings = MagicMock()
    shared.kg = MagicMock()

    fake_handler = AsyncMock(return_value="## Retrieved Knowledge (2 results)\n\nFact A\nFact B")
    mock_factory = MagicMock(return_value=fake_handler)

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        result = await retrieve_context(
            query="homeostatic models",
            namespace="paradigm",
            top_k=3,
            stage="phase2-architect",
            run_id="test-run-id",
        )

    # Factory called with correct infra singletons
    mock_factory.assert_called_once()
    call_kwargs = mock_factory.call_args.kwargs
    assert call_kwargs["kg"] is shared.kg
    assert call_kwargs["vector_store"] is shared.vectors
    assert call_kwargs["embedding_service"] is shared.embeddings
    assert call_kwargs["search_adapter"] is None
    assert call_kwargs["run_id"] == "test-run-id"
    assert call_kwargs["stage"] == "phase2-architect"

    # Handler called with params dict
    fake_handler.assert_awaited_once()
    params = fake_handler.await_args.args[0]
    assert params["query"] == "homeostatic models"
    assert params["namespace"] == "paradigm"
    assert params["top_k"] == 3

    # Result is the handler's output
    assert result == "## Retrieved Knowledge (2 results)\n\nFact A\nFact B"


async def test_namespace_none_not_passed_in_params():
    """When namespace is None, it is omitted from the params dict."""
    shared.vectors = MagicMock()
    fake_handler = AsyncMock(return_value="result")
    mock_factory = MagicMock(return_value=fake_handler)

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        await retrieve_context(query="test", namespace=None)

    params = fake_handler.await_args.args[0]
    assert "namespace" not in params


async def test_as_of_passed_when_provided():
    """When as_of is provided, it appears in the params dict."""
    shared.vectors = MagicMock()
    fake_handler = AsyncMock(return_value="result")
    mock_factory = MagicMock(return_value=fake_handler)

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        await retrieve_context(query="test", as_of="2026-01-15T00:00:00Z")

    params = fake_handler.await_args.args[0]
    assert params["as_of"] == "2026-01-15T00:00:00Z"


async def test_as_of_omitted_when_none():
    """When as_of is None, it is omitted from the params dict."""
    shared.vectors = MagicMock()
    fake_handler = AsyncMock(return_value="result")
    mock_factory = MagicMock(return_value=fake_handler)

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        await retrieve_context(query="test", as_of=None)

    params = fake_handler.await_args.args[0]
    assert "as_of" not in params


async def test_run_id_auto_generated_when_not_provided():
    """When run_id is omitted, a UUID is generated."""
    shared.vectors = MagicMock()
    mock_factory = MagicMock(return_value=AsyncMock(return_value="ok"))

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        await retrieve_context(query="test")

    run_id = mock_factory.call_args.kwargs["run_id"]
    assert isinstance(run_id, str)
    assert len(run_id) == 36  # UUID format


async def test_default_stage_is_phase2():
    """Default stage parameter is 'phase2'."""
    shared.vectors = MagicMock()
    mock_factory = MagicMock(return_value=AsyncMock(return_value="ok"))

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
    ):
        await retrieve_context(query="test")

    assert mock_factory.call_args.kwargs["stage"] == "phase2"


async def test_handler_exception_returns_empty_and_logs(caplog):
    """If the handler itself raises, wrapper catches and returns empty."""
    shared.vectors = MagicMock()
    fake_handler = AsyncMock(side_effect=RuntimeError("network error"))
    mock_factory = MagicMock(return_value=fake_handler)

    with (
        patch(_SETTINGS_PATH, return_value=_FLAG_ON),
        patch(_FACTORY_PATH, mock_factory),
        caplog.at_level("ERROR", logger="simlab.recall.retrieve"),
    ):
        result = await retrieve_context(query="test")

    assert result == _EMPTY_RESULT
    assert any("retrieve_context failed" in r.message for r in caplog.records)
