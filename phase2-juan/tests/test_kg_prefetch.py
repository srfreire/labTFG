"""P1-001 — tests for prefetch_knowledge function.

Mocks retrieve_context so no real KG infrastructure is needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from simlab.orchestrator import prefetch_knowledge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY = "## Retrieved Knowledge (0 results)\n\nNo results found."
_POSTULATES = "## Retrieved Knowledge (2 results)\n\n### Result 1\nPostulate P1: ..."
_SIMULATION = "## Retrieved Knowledge (1 results)\n\n### Result 1\nPrevious sim ..."
_PAPERS = "## Retrieved Knowledge (3 results)\n\n### Result 1\nSmith et al. 2024 ..."


# ---------------------------------------------------------------------------
# Analyst stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_analyst_parallel():
    """Analyst stage: 2 parallel queries (paradigm + simulation)."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _SIMULATION])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("prospect_theory", "analyst")

    assert mock_rc.call_count == 2
    assert "## Knowledge context" in result
    assert "### Postulates" in result
    assert "### Historical simulations" in result
    assert _POSTULATES in result
    assert _SIMULATION in result


@pytest.mark.asyncio
async def test_prefetch_analyst_omits_empty_subsection():
    """If one query returns empty, its subsection is omitted."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _EMPTY])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("prospect_theory", "analyst")

    assert "### Postulates" in result
    assert "### Historical simulations" not in result


# ---------------------------------------------------------------------------
# Reporter stage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_reporter():
    """Reporter stage: 1 query (meta, top_k=10)."""
    mock_rc = AsyncMock(return_value=_PAPERS)

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("prospect_theory", "reporter")

    mock_rc.assert_called_once()
    call_kwargs = mock_rc.call_args.kwargs
    assert call_kwargs["namespace"] == "meta"
    assert call_kwargs["top_k"] == 10
    assert "## Knowledge context" in result
    assert "### References" in result


# ---------------------------------------------------------------------------
# Failure scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_partial_failure():
    """One query fails, other succeeds — return successful + emit warning."""
    mock_rc = AsyncMock(side_effect=[RuntimeError("connection refused"), _SIMULATION])
    on_warning = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("prospect_theory", "analyst", on_warning=on_warning)

    on_warning.assert_called_once()
    assert on_warning.call_args[0][0] == "analyst"
    assert "connection refused" in on_warning.call_args[0][1]
    assert "### Historical simulations" in result
    assert "### Postulates" not in result


@pytest.mark.asyncio
async def test_prefetch_total_failure():
    """All queries fail — return '' + emit warnings."""
    mock_rc = AsyncMock(side_effect=[RuntimeError("fail1"), RuntimeError("fail2")])
    on_warning = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("prospect_theory", "analyst", on_warning=on_warning)

    assert result == ""
    assert on_warning.call_count == 2


# ---------------------------------------------------------------------------
# Guard clauses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_disabled():
    """ENABLE_KNOWLEDGE_READ=False -> '' without calling retrieve_context."""
    mock_rc = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = False
        result = await prefetch_knowledge("prospect_theory", "analyst")

    assert result == ""
    mock_rc.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_no_paradigm():
    """Empty paradigm -> '' without calling retrieve_context."""
    mock_rc = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
        patch("shared.settings.load_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_KNOWLEDGE_READ = True
        result = await prefetch_knowledge("", "analyst")

    assert result == ""
    mock_rc.assert_not_called()
