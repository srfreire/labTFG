import json

import pytest
from unittest.mock import AsyncMock

from decisionlab.agents.builder_sub import (
    BuilderSubAgent,
    BUILDER_SUB_SYSTEM_PROMPT,
)


def test_system_prompt_exists():
    assert "DecisionModel" in BUILDER_SUB_SYSTEM_PROMPT
    assert "Action" in BUILDER_SUB_SYSTEM_PROMPT


def test_builder_sub_has_correct_tools(tmp_path):
    client = AsyncMock()
    agent = BuilderSubAgent(
        client=client,
        models_prefix="models/run-1",
        project_root=tmp_path,
    )
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "run_tests" in tool_names


@pytest.mark.asyncio
async def test_builder_sub_run_returns_content(
    tmp_path, make_tool_use_block, make_text_block, make_response,
):
    spec = {
        "formulation_id": "pi_controller",
        "paradigm": "homeostatic",
        "name": "Homeostatic PI Controller",
        "description": "A PI controller for homeostatic regulation.",
        "variables": [
            {"symbol": "F", "name": "fat_reserves", "description": "Body fat", "type": "float", "initial_value": 50.0, "range": [0, 100]}
        ],
        "parameters": [
            {"symbol": "cF", "name": "fat_conversion_rate", "default": 0.3, "source": "Jacquier et al., 2014"}
        ],
        "rules": [
            {"id": "R1", "description": "Fat update", "type": "ODE", "pseudocode": "dF_dt = cF * intake - alphaF * F", "source_postulate": "P1"}
        ],
        "decision_logic": {
            "description": "Hunger-based decision",
            "pseudocode": ["if hunger > threshold: return Action('eat')", "else: return Action('stay')"]
        },
        "env_mapping": {
            "perception_to_variables": {"food_sources": "perception.resources.food"},
            "actions_used": ["eat", "stay"],
            "reward_source": "eat action"
        },
        "expected_behaviors": [
            {"id": "B1", "description": "Hunger increases without eating", "test_pseudocode": "run 10 steps without food → assert hunger increases"}
        ],
        "references": []
    }

    # Step 1: LLM calls read_file for the spec (nested path)
    read_spec = make_tool_use_block(
        "call_1", "read_file", {"path": "reasoner/homeostatic/pi_controller.json"}
    )
    resp1 = make_response("tool_use", [read_spec])

    # Step 2: LLM calls write_file with the model (nested path)
    write_model = make_tool_use_block(
        "call_2",
        "write_file",
        {
            "path": "builder/homeostatic/pi_controller_model.py",
            "content": "# model implementation\nclass HomeostaticPiControllerModel:\n    pass\n",
        },
    )
    resp2 = make_response("tool_use", [write_model])

    # Step 3: LLM calls write_file with tests (nested path)
    write_tests = make_tool_use_block(
        "call_3",
        "write_file",
        {
            "path": "builder/homeostatic/test_pi_controller.py",
            "content": "# tests\ndef test_placeholder(): pass\n",
        },
    )
    resp3 = make_response("tool_use", [write_tests])

    # Step 4: LLM calls run_tests
    run_tests_call = make_tool_use_block(
        "call_4",
        "run_tests",
        {"path": "builder/homeostatic/test_pi_controller.py"},
    )
    resp4 = make_response("tool_use", [run_tests_call])

    # Step 5: LLM produces final summary
    final_text = make_text_block(
        "Implemented pi_controller model and all tests passed."
    )
    resp5 = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.side_effect = [resp1, resp2, resp3, resp4, resp5]

    agent = BuilderSubAgent(
        client=client,
        models_prefix="models/run-1",
        project_root=tmp_path,
    )
    result = await agent.run(
        "pi_controller",
        "reasoner/homeostatic/pi_controller.json",
    )

    assert "pi_controller" in result


# ---- P5-003: Slug-based path tests ----


def test_system_prompt_uses_nested_builder_paths():
    """System prompt should instruct writing to builder/{paradigm_slug}/{formulation_slug}_model.py."""
    assert "builder/{paradigm_slug}/{formulation_slug}_model.py" in BUILDER_SUB_SYSTEM_PROMPT
    assert "builder/{paradigm_slug}/test_{formulation_slug}.py" in BUILDER_SUB_SYSTEM_PROMPT


def test_system_prompt_uses_nested_validation_path():
    """System prompt should use builder/{paradigm_slug}/{formulation_slug}_validation.json."""
    assert "builder/{paradigm_slug}/{formulation_slug}_validation.json" in BUILDER_SUB_SYSTEM_PROMPT


# ---- P4-002: Validation tests ----


def test_system_prompt_contains_validation_step():
    """System prompt must include a validation phase before code generation."""
    prompt_lower = BUILDER_SUB_SYSTEM_PROMPT.lower()
    assert "validation" in prompt_lower
    assert "invalid" in prompt_lower
    assert "problems" in prompt_lower


def test_system_prompt_lists_validation_checks():
    """System prompt must list the specific implementability checks."""
    assert "ambiguous_logic" in BUILDER_SUB_SYSTEM_PROMPT
    assert "missing_perception_key" in BUILDER_SUB_SYSTEM_PROMPT
    assert "untestable_behavior" in BUILDER_SUB_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_builder_sub_uses_sonnet_model(tmp_path, make_text_block, make_response):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = BuilderSubAgent(
        client=client,
        models_prefix="models/run-1",
        project_root=tmp_path,
    )
    await agent.run("pi_controller", "reasoner/homeostatic/pi_controller.json")

    from decisionlab.config import SETTINGS
    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == SETTINGS.builder.model
