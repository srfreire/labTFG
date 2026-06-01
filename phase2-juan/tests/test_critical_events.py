"""Tests for rule-based critical event detection."""

from __future__ import annotations

from simlab.critical_events import critical_events_to_json, detect_critical_events
from simlab.environment import Action, Event


def test_detects_death_from_terminated_action_result():
    events = [
        Event(
            step=49,
            agent_id="homeostatic",
            action=Action("move_right"),
            outcome={
                "action_result": {
                    "terminated": True,
                    "termination_reason": "energy_depleted",
                },
                "reward": -1.0,
                "model_state": {"energy": 0.0},
            },
        )
    ]

    critical = critical_events_to_json(detect_critical_events(events))

    death = [event for event in critical if event["type"] == "death"]
    assert death == [
        {
            "step": 49,
            "agent_id": "homeostatic",
            "type": "death",
            "severity": 1.0,
            "description": "homeostatic terminó la simulación: energy_depleted",
            "data": {"termination_reason": "energy_depleted", "energy": 0.0},
        }
    ]
