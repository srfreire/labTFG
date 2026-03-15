"""Integration tests for the Architect agent (requires ANTHROPIC_API_KEY)."""
import asyncio
import json
import os

import pytest

from simlab.architect import run_architect
from simlab.spec import validate_spec_dict, spec_to_environment

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)


@pytest.mark.integration
def test_architect_generates_valid_spec():
    prompt = "Grid 10x10 with food that regenerates. Agents can move in 4 directions and eat."
    result = asyncio.run(run_architect(prompt))

    spec = json.loads(result)

    errors = validate_spec_dict(spec)
    assert errors == [], f"Validation errors: {errors}"

    env = spec_to_environment(spec, seed=42)
    assert env.width == 10
    assert env.height == 10


@pytest.mark.integration
def test_architect_handles_complex_prompt():
    prompt = (
        "A 20x20 world with two resource types: food (palatability 0.1-1.0, 5 instances, regenerates) "
        "and water (purity 0.5-1.0, 3 instances, does not regenerate). "
        "Agents can move in 4 directions, eat food, drink water, and rest."
    )
    result = asyncio.run(run_architect(prompt))
    spec = json.loads(result)

    errors = validate_spec_dict(spec)
    assert errors == [], f"Validation errors: {errors}"

    env = spec_to_environment(spec, seed=42)
    assert "food" in env._resource_rules
    assert "water" in env._resource_rules
