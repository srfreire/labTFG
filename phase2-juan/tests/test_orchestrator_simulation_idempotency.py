"""Tests for run_simulation idempotency helpers."""

from __future__ import annotations

import json

from simlab.orchestrator import _simulation_request_signature


def test_simulation_signature_is_stable_for_equivalent_requests():
    spec = {
        "grid": {"width": 8, "height": 8},
        "actions": [{"name": "stay", "effect": {"type": "NoopEffect"}}],
        "resources": [{"type": "food", "count": 5, "properties": {}}],
    }
    params = {
        "steps": 100,
        "seed": 7,
        "num_agents": 1,
        "model_ids": [
            "homeostatic-regulation/drive-reduction-rl",
            "reinforcement-learning/tabular-q-learning-with-greedy-action-selection",
        ],
    }

    assert _simulation_request_signature(spec, params) == json.dumps(
        {
            "model_ids": params["model_ids"],
            "num_agents": 1,
            "seed": 7,
            "spec": spec,
            "steps": 100,
        },
        sort_keys=True,
        default=str,
    )


def test_simulation_signature_changes_when_steps_change():
    spec = {"grid": {"width": 8, "height": 8}}
    first = _simulation_request_signature(spec, {"steps": 100})
    second = _simulation_request_signature(spec, {"steps": 200})

    assert first != second
