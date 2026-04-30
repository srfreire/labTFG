"""P1-001 / P1-004 — tests for prefetch_knowledge and agent injection.

Mocks retrieve_context so no real KG infrastructure is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.environment import Action, Event
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
    ):
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
    ):
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
    ):
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
    ):
        result = await prefetch_knowledge(
            "prospect_theory", "analyst", on_warning=on_warning
        )

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
    ):
        result = await prefetch_knowledge(
            "prospect_theory", "analyst", on_warning=on_warning
        )

    assert result == ""
    assert on_warning.call_count == 2


# ---------------------------------------------------------------------------
# Guard clauses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_disabled():
    """enabled=False -> '' without calling retrieve_context."""
    mock_rc = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "analyst", enabled=False)

    assert result == ""
    mock_rc.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_no_paradigm():
    """Empty paradigm -> '' without calling retrieve_context."""
    mock_rc = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("", "analyst")

    assert result == ""
    mock_rc.assert_not_called()


# ---------------------------------------------------------------------------
# Architect stage (P2-002)
# ---------------------------------------------------------------------------

_PARADIGM_FACTS = (
    "## Retrieved Knowledge (2 results)\n\n### Result 1\nProspect theory facts..."
)
_PREV_ENVS = (
    "## Retrieved Knowledge (1 results)\n\n### Result 1\nGrid 10x10 with resources..."
)


@pytest.mark.asyncio
async def test_prefetch_architect():
    """Architect stage: 2 parallel queries (paradigm + simulation)."""
    mock_rc = AsyncMock(side_effect=[_PARADIGM_FACTS, _PREV_ENVS])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect theory with 5 agents", "architect")

    assert mock_rc.call_count == 2
    assert "## Knowledge context" in result
    assert "### Paradigm facts" in result
    assert "### Previous environments" in result


@pytest.mark.asyncio
async def test_architect_knowledge_context_injected():
    """Architect user message includes knowledge context after prompt."""
    from simlab.architect import Architect

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.architect.run_agent_loop", side_effect=fake_loop):
        arch = Architect(client=MagicMock())
        await arch.run("design an environment", knowledge_context=_KNOWLEDGE_CTX)

    msg = captured["messages"][0]["content"]
    assert "design an environment" in msg
    assert "## Knowledge context" in msg
    prompt_pos = msg.index("design an environment")
    ctx_pos = msg.index("## Knowledge context")
    assert prompt_pos < ctx_pos


@pytest.mark.asyncio
async def test_architect_no_knowledge_context():
    """Architect without knowledge_context — message is just the prompt."""
    from simlab.architect import Architect

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.architect.run_agent_loop", side_effect=fake_loop):
        arch = Architect(client=MagicMock())
        await arch.run("design an environment")

    msg = captured["messages"][0]["content"]
    assert msg == "design an environment"
    assert "## Knowledge context" not in msg


# ---------------------------------------------------------------------------
# R2: Agent injection tests (P1-004)
# ---------------------------------------------------------------------------

_FAKE_EVENT = Event(step=0, agent_id="a1", action=Action(name="move"))
_KNOWLEDGE_CTX = "## Knowledge context\n\n### Postulates\nSome postulate data"


def _mock_response():
    """Create a minimal mock response from run_agent_loop."""
    block = MagicMock()
    block.type = "text"
    block.text = '{"patterns": [], "comparisons": [], "metrics": {}}'
    resp = MagicMock()
    resp.content = [block]
    return resp


@pytest.mark.asyncio
async def test_analyst_knowledge_context_injected():
    """Analyst user message includes knowledge context before tracker output."""
    from simlab.analyst import Analyst

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.analyst.run_agent_loop", side_effect=fake_loop):
        analyst = Analyst(client=MagicMock())
        await analyst.run(
            "Analyze",
            "tracker data",
            [_FAKE_EVENT],
            knowledge_context=_KNOWLEDGE_CTX,
        )

    msg = captured["messages"][0]["content"]
    ctx_pos = msg.index("## Knowledge context")
    tracker_pos = msg.index("## Tracker observation log")
    assert ctx_pos < tracker_pos


@pytest.mark.asyncio
async def test_analyst_no_knowledge_context():
    """Analyst without knowledge_context has no such section."""
    from simlab.analyst import Analyst

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.analyst.run_agent_loop", side_effect=fake_loop):
        analyst = Analyst(client=MagicMock())
        await analyst.run("Analyze", "tracker data", [_FAKE_EVENT])

    msg = captured["messages"][0]["content"]
    assert "## Knowledge context" not in msg
    assert "## Tracker observation log" in msg


@pytest.mark.asyncio
async def test_reporter_knowledge_context_injected():
    """Reporter user message includes knowledge context before tracker output."""
    from simlab.reporter import Reporter

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.reporter.run_agent_loop", side_effect=fake_loop):
        reporter = Reporter(client=MagicMock())
        await reporter.run(
            "Report",
            "tracker data",
            "analyst data",
            run_id="r1",
            experiment_id="e1",
            knowledge_context=_KNOWLEDGE_CTX,
        )

    msg = captured["messages"][0]["content"]
    ctx_pos = msg.index("## Knowledge context")
    tracker_pos = msg.index("## Tracker observation log")
    assert ctx_pos < tracker_pos


@pytest.mark.asyncio
async def test_reporter_no_knowledge_context():
    """Reporter without knowledge_context has no such section."""
    from simlab.reporter import Reporter

    captured = {}

    async def fake_loop(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _mock_response()

    with patch("simlab.reporter.run_agent_loop", side_effect=fake_loop):
        reporter = Reporter(client=MagicMock())
        await reporter.run(
            "Report",
            "tracker data",
            "analyst data",
            run_id="r1",
            experiment_id="e1",
        )

    msg = captured["messages"][0]["content"]
    assert "## Knowledge context" not in msg
    assert "## Tracker observation log" in msg


# ---------------------------------------------------------------------------
# R3: Integration roundtrip (P1-004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_roundtrip():
    """Full flow: prefetch → format → verify structure for agent injection."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _SIMULATION])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        knowledge_ctx = await prefetch_knowledge("prospect_theory", "analyst")

    # Simulate what the orchestrator does: inject into analyst user message
    prompt = "Analyze patterns"
    tracker_output = "Step 1: agent moved north"
    parts = [prompt]
    if knowledge_ctx:
        parts.append(knowledge_ctx)
    parts.append(f"## Tracker observation log\n\n{tracker_output}")
    user_message = "\n\n".join(parts)

    # Verify structure
    assert user_message.startswith("Analyze patterns")
    assert "## Knowledge context" in user_message
    assert "### Postulates" in user_message
    assert "### Historical simulations" in user_message
    ctx_pos = user_message.index("## Knowledge context")
    tracker_pos = user_message.index("## Tracker observation log")
    assert ctx_pos < tracker_pos
