"""P2-003 — tests for the knowledge-writer integration in observe_simulation.

These exercise the closure returned by `Orchestrator._build_tools()`; they
patch the `Tracker` class so no LLM is called, and patch
`shared.sim_memory_writer` to assert the writer is invoked (or not) as
specified. No real infra required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import shared
from simlab.knowledge import WriteResult
from simlab.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_writer_singleton():
    """Keep tests isolated — the singleton is module-level global."""
    original = getattr(shared, "sim_memory_writer", None)
    shared.sim_memory_writer = None
    yield
    shared.sim_memory_writer = original


def _tracker_json() -> str:
    return json.dumps({
        "summary": "Mock tracker output for testing.",
        "trajectories": {
            "f-a_0": {"steps_survived": 10, "resources_consumed": 1, "actions": {"x": 5}},
        },
        "episodes": [
            {"agent": "f-a_0", "type": "starvation", "step": 10, "description": "done"},
        ],
    })


def _prepopulated_state(experiment_id: str | None = None) -> dict:
    """State as it would be after a successful `run_simulation`."""
    return {
        "events": [object()],  # truthy list — content doesn't matter, Tracker is mocked
        "spec": {"grid_width": 10, "grid_height": 8},
        "replay": {"frames": [None] * 25},
        "agent_to_model": {
            "f-a_0": {
                "model_id": "m-1",
                "class_name": "ModelA",
                "paradigm": "p",
                "formulation": "f-a",
                "phase1_run_id": "r-1",
            },
        },
        "seed": 7,
        "experiment_id": experiment_id,
        "critical_events": None,
    }


def _make_orchestrator():
    """Build an Orchestrator with a mocked Anthropic client."""
    return Orchestrator(client=MagicMock())


async def _run_observe(state: dict) -> tuple[str, object]:
    """Run observe_simulation with a mocked Tracker that returns _tracker_json()."""
    orch = _make_orchestrator()
    orch._state.update(state)
    _, registry = orch._build_tools()

    mock_tracker = MagicMock()
    mock_tracker.run = AsyncMock(return_value=_tracker_json())
    with patch("simlab.orchestrator.Tracker", return_value=mock_tracker):
        result = await registry["observe_simulation"]({})
    return result, mock_tracker


# ---------------------------------------------------------------------------
# 1. Happy path — writer is invoked with a well-formed SimulationContext
# ---------------------------------------------------------------------------


async def test_observe_simulation_invokes_writer_when_set():
    writer = MagicMock()
    writer.write = AsyncMock(return_value=WriteResult(
        summaries_written=1, trajectories_written=1, episodes_written=1,
        episodes_filtered=0, duration_ms=3, skipped_reason=None,
    ))
    shared.sim_memory_writer = writer

    result, _ = await _run_observe(_prepopulated_state(experiment_id=None))

    writer.write.assert_awaited_once()
    tracker_arg, context_arg = writer.write.await_args.args
    assert tracker_arg == _tracker_json()
    # experiment_id absent → empty string via str(None or "") fallback
    assert context_arg.phase2_experiment_id == ""
    assert context_arg.environment == "grid_10x8"
    assert context_arg.steps == 25
    assert context_arg.seed == 7
    assert "f-a_0" in context_arg.agent_to_model
    assert context_arg.agent_to_model["f-a_0"].paradigm == "p"
    # tracker result still returned unchanged
    assert result == _tracker_json()


# ---------------------------------------------------------------------------
# 2. Writer not set (flag OFF) — observe_simulation behaves identically
# ---------------------------------------------------------------------------


async def test_observe_simulation_skips_when_writer_is_none():
    shared.sim_memory_writer = None

    # Should NOT touch any writer and must return the tracker output unchanged.
    result, mock_tracker = await _run_observe(_prepopulated_state(experiment_id=None))

    assert result == _tracker_json()
    mock_tracker.run.assert_awaited_once()


# ---------------------------------------------------------------------------
# 3. Writer raises — observe_simulation logs and returns normally
# ---------------------------------------------------------------------------


async def test_observe_simulation_swallows_writer_exception(caplog):
    writer = MagicMock()
    writer.write = AsyncMock(side_effect=RuntimeError("boom"))
    shared.sim_memory_writer = writer

    with caplog.at_level("ERROR", logger="simlab.orchestrator"):
        result, _ = await _run_observe(_prepopulated_state(experiment_id=None))

    assert result == _tracker_json()
    assert any("knowledge writer raised" in r.message for r in caplog.records)
