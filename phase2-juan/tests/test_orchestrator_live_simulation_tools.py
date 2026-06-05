"""Tests for Orchestrator live simulation detail tools."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from simlab.environment import Action, Event
from simlab.orchestrator import Orchestrator


def _event(step: int, agent_id: str, action: str, reward: float = 0.0) -> Event:
    return Event(
        step=step,
        agent_id=agent_id,
        action=Action(name=action),
        outcome={
            "reward": reward,
            "action_result": {"ok": True},
            "model_state": {"energy": 100 - step},
            "perception": {"step": step},
            "pre_state": {"energy": 101 - step},
        },
    )


async def test_get_simulation_step_window_reads_latest_run_without_tracker():
    orch = Orchestrator(client=MagicMock(), services=MagicMock())
    orch._state["experiment_id"] = "exp-live"
    orch._state["events"] = [
        _event(0, "agent_a", "move_up"),
        _event(1, "agent_a", "eat", 1.0),
        _event(2, "agent_a", "move_down"),
        _event(2, "agent_b", "stay"),
        _event(3, "agent_a", "move_left"),
    ]
    orch._state["critical_events"] = [
        {
            "step": 2,
            "agent_id": "agent_b",
            "type": "starvation",
            "severity": 0.8,
            "description": "agent_b energia critica",
        }
    ]

    _, registry = orch._build_tools()

    result = json.loads(
        await registry["get_simulation_step_window"]({"center_step": 2, "radius": 1})
    )

    assert result["experiment_id"] == "exp-live"
    assert result["center_step"] == 2
    assert result["step_range"] == [1, 3]
    assert [e["step"] for e in result["events"]] == [1, 2, 2, 3]
    assert result["critical_events"][0]["step"] == 2
    assert "perception" not in result["events"][0]


async def test_get_simulation_step_window_errors_before_run():
    orch = Orchestrator(client=MagicMock(), services=MagicMock())
    _, registry = orch._build_tools()

    result = json.loads(
        await registry["get_simulation_step_window"]({"center_step": 2})
    )

    assert "error" in result
    assert "run_simulation" in result["error"]


async def test_get_report_links_returns_download_urls_for_current_reports():
    orch = Orchestrator(client=MagicMock(), services=MagicMock())
    orch._state["pdf_paths"] = [
        "experiments/exp-1/informe_final.pdf",
        "experiments/exp-1/comparativa_modelos.pdf",
    ]

    _, registry = orch._build_tools()

    result = json.loads(await registry["get_report_links"]({}))

    assert result == {
        "reports": [
            {
                "key": "experiments/exp-1/informe_final.pdf",
                "filename": "informe_final.pdf",
                "download_url": "/api/reports/download?key=experiments%2Fexp-1%2Finforme_final.pdf",
            },
            {
                "key": "experiments/exp-1/comparativa_modelos.pdf",
                "filename": "comparativa_modelos.pdf",
                "download_url": "/api/reports/download?key=experiments%2Fexp-1%2Fcomparativa_modelos.pdf",
            },
        ]
    }
