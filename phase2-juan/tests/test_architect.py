"""Integration tests for the Architect agent (requires ANTHROPIC_API_KEY)."""
import asyncio
import json
import os

import anthropic
import pytest

from simlab.architect import Architect
from simlab.spec import validate_spec_dict, spec_to_environment

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)


def _run(prompt: str) -> str:
    """Helper: create a client, run the Architect, return the result."""
    client = anthropic.AsyncAnthropic()
    architect = Architect(client=client)
    return asyncio.run(architect.run(prompt))


@pytest.mark.integration
def test_architect_generates_valid_spec():
    result = _run("Grid 10x10 with food that regenerates. Agents can move in 4 directions and eat.")

    spec = json.loads(result)
    errors = validate_spec_dict(spec)
    assert errors == [], f"Validation errors: {errors}"

    env = spec_to_environment(spec, seed=42)
    assert env.width == 10
    assert env.height == 10


@pytest.mark.integration
def test_architect_handles_complex_prompt():
    result = _run(
        "A 20x20 world with two resource types: food (palatability 0.1-1.0, 5 instances, regenerates) "
        "and water (purity 0.5-1.0, 3 instances, does not regenerate). "
        "Agents can move in 4 directions, eat food, drink water, and rest."
    )
    spec = json.loads(result)

    errors = validate_spec_dict(spec)
    assert errors == [], f"Validation errors: {errors}"

    env = spec_to_environment(spec, seed=42)
    assert "food" in env._resource_rules
    assert "water" in env._resource_rules
