"""Tests for the deterministic grounding layer.

The Tracker/Analyst copy structured aggregates correctly but fabricate counts in
free prose (judge-cited: "60 de 72 acciones totales" when the true split is 50 of
60; "58 de 60" when it is 46 of 60). These tests pin the corrective rewriting.
"""

from __future__ import annotations

import json

from simlab.environment import Action, Event
from simlab.grounding import (
    agent_action_facts,
    lint_analyst_output,
    lint_tracker_output,
)


def _events(agent_id: str, actions: list[str]) -> list[Event]:
    return [
        Event(step=i, agent_id=agent_id, action=Action(name))
        for i, name in enumerate(actions)
    ]


def _hierarchical_events() -> list[Event]:
    # 50 moves + 10 stay = 60 total (matches CASO2 ground truth)
    actions = (
        ["move_down"] * 16
        + ["move_up"] * 14
        + ["move_right"] * 12
        + ["move_left"] * 8
        + ["stay"] * 10
    )
    return _events("hierarchical", actions)


def _hrl_events() -> list[Event]:
    # 46 moves + 12 stay + 2 eat = 60 total
    actions = (
        ["move_up"] * 14
        + ["move_down"] * 13
        + ["move_right"] * 12
        + ["move_left"] * 7
        + ["stay"] * 12
        + ["eat"] * 2
    )
    return _events("hrl", actions)


def test_agent_action_facts_counts_moves_and_total():
    facts = agent_action_facts(_hierarchical_events())
    rec = facts["hierarchical"]
    assert rec["total"] == 60
    assert rec["moves"] == 50
    assert rec["stay"] == 10


def test_tracker_episode_count_fabrication_is_corrected():
    tracker = json.dumps(
        {
            "summary": "x",
            "trajectories": {},
            "episodes": [
                {
                    "agent": "hierarchical",
                    "type": "foraging_failure",
                    "steps": [0, 60],
                    "description": (
                        "Exploración infructuosa: 83% de acciones fueron "
                        "movimiento (60 de 72 acciones totales), sin consumo."
                    ),
                }
            ],
        }
    )
    out, corrections = lint_tracker_output(tracker, _hierarchical_events())
    data = json.loads(out)
    desc = data["episodes"][0]["description"]
    assert "50 de 60" in desc
    assert "60 de 72" not in desc
    assert corrections  # a correction was recorded


def test_analyst_pattern_count_fabrication_is_corrected():
    analyst = json.dumps(
        {
            "patterns": [
                {
                    "id": "P2",
                    "agents": ["hrl"],
                    "description": (
                        "Mantuvo 80% de acciones de movimiento (58 de 60) "
                        "distribuyéndose entre direcciones."
                    ),
                    "evidence": "Total de movimiento alto.",
                }
            ],
            "comparisons": [],
            "metrics": {},
        }
    )
    out, corrections = lint_analyst_output(analyst, _hrl_events())
    data = json.loads(out)
    desc = data["patterns"][0]["description"]
    assert "46 de 60" in desc
    assert "58 de 60" not in desc
    assert corrections


def test_bare_movement_total_corrected_via_breakdown():
    # CASO2 residual: "52 movimientos" while the listed breakdown sums to 50.
    tracker = json.dumps(
        {
            "episodes": [
                {
                    "agent": "hierarchical",
                    "type": "foraging_failure",
                    "description": (
                        "Fracaso total: 52 movimientos distribuidos entre "
                        "direcciones (12 right, 14 up, 16 down, 8 left) con 10 "
                        "stays, sin convergencia."
                    ),
                }
            ]
        }
    )
    out, corrections = lint_tracker_output(tracker, _hierarchical_events())
    desc = json.loads(out)["episodes"][0]["description"]
    assert "50 movimientos" in desc
    assert "52 movimientos" not in desc
    assert corrections


def test_breakdown_rule_ignores_windowed_movement_counts():
    # A windowed "13 movimientos en 24 pasos" with no breakdown must be left alone.
    tracker = json.dumps(
        {
            "episodes": [
                {
                    "agent": "hierarchical",
                    "type": "exploration",
                    "description": "Exploración: 13 movimientos en los primeros 24 pasos.",
                }
            ]
        }
    )
    out, corrections = lint_tracker_output(tracker, _hierarchical_events())
    assert "13 movimientos" in json.loads(out)["episodes"][0]["description"]
    assert not corrections


def test_does_not_touch_non_action_de_numbers():
    # "paso 6 de 60" is a step reference, not an action count — must be left alone.
    tracker = json.dumps(
        {
            "episodes": [
                {
                    "agent": "hierarchical",
                    "type": "starvation",
                    "description": "Murió en el paso 6 de 60 tras agotar energía.",
                }
            ]
        }
    )
    out, corrections = lint_tracker_output(tracker, _hierarchical_events())
    data = json.loads(out)
    assert "paso 6 de 60" in data["episodes"][0]["description"]
    assert not corrections


def test_skips_multi_agent_patterns():
    # When a pattern is attributed to two agents, whose count is "(58 de 60)"?
    # Ambiguous — leave it for prompt-level handling, do not guess.
    analyst = json.dumps(
        {
            "patterns": [
                {
                    "id": "P5",
                    "agents": ["hrl", "hierarchical"],
                    "description": "Ambos modelos movieron (58 de 60) las veces.",
                    "evidence": "x",
                }
            ]
        }
    )
    out, corrections = lint_analyst_output(
        analyst, _hrl_events() + _hierarchical_events()
    )
    assert not corrections
    assert "58 de 60" in json.loads(out)["patterns"][0]["description"]


def test_malformed_json_is_returned_untouched():
    out, corrections = lint_tracker_output("not json{", _hierarchical_events())
    assert out == "not json{"
    assert not corrections
