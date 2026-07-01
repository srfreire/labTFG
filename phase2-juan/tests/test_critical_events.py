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


def test_confidence_drop_description_has_no_unverifiable_number():
    import re

    events = [
        Event(
            step=10,
            agent_id="qlearner",
            action=Action("move_up"),
            pre_state={"q_values": {"move_up": 0.80, "stay": 0.10}},  # gap 0.70
        ),
        Event(
            step=11,
            agent_id="qlearner",
            action=Action("stay"),
            pre_state={"q_values": {"move_up": 0.42, "stay": 0.40}},  # gap 0.02
        ),
    ]

    critical = critical_events_to_json(detect_critical_events(events))
    drops = [c for c in critical if c["type"] == "decision_confidence_drop"]

    assert len(drops) == 1
    assert not re.search(r"\d\.\d", drops[0]["description"])  # no decimal in prose
    assert "prev_gap" not in drops[0]["data"]
    assert "new_gap" not in drops[0]["data"]
    assert drops[0]["data"] == {}
