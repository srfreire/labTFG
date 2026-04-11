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
    agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "run_tests" in tool_names


@pytest.mark.asyncio
async def test_builder_sub_run_returns_content(
    tmp_path, make_tool_use_block, make_text_block, make_response,
):
    spec = {
        "formulation_id": "homeostatic_pi_controller",
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

    # Set up fixture spec file
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir(parents=True)
    spec_path = reasoner_dir / "homeostatic_pi_controller.json"
    spec_path.write_text(json.dumps(spec, indent=2))

    # Step 1: LLM calls read_file for the spec
    read_spec = make_tool_use_block(
        "call_1", "read_file", {"path": "reasoner/homeostatic_pi_controller.json"}
    )
    resp1 = make_response("tool_use", [read_spec])

    # Step 2: LLM calls write_file with the model implementation
    write_model = make_tool_use_block(
        "call_2",
        "write_file",
        {
            "path": "builder/homeostatic_pi_controller_model.py",
            "content": "# model implementation\nclass HomeostaticPiControllerModel:\n    pass\n",
        },
    )
    resp2 = make_response("tool_use", [write_model])

    # Step 3: LLM calls write_file with tests
    write_tests = make_tool_use_block(
        "call_3",
        "write_file",
        {
            "path": "builder/test_homeostatic_pi_controller.py",
            "content": "# tests\ndef test_placeholder(): pass\n",
        },
    )
    resp3 = make_response("tool_use", [write_tests])

    # Step 4: LLM calls run_tests
    run_tests_call = make_tool_use_block(
        "call_4",
        "run_tests",
        {"path": "builder/test_homeostatic_pi_controller.py"},
    )
    resp4 = make_response("tool_use", [run_tests_call])

    # Step 5: LLM produces final summary
    final_text = make_text_block(
        "Implemented homeostatic_pi_controller model and all tests passed."
    )
    resp5 = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.side_effect = [resp1, resp2, resp3, resp4, resp5]

    agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
    result = await agent.run(
        "homeostatic_pi_controller",
        "reasoner/homeostatic_pi_controller.json",
    )

    assert "homeostatic_pi_controller" in result


@pytest.mark.asyncio
async def test_builder_sub_uses_sonnet_model(tmp_path, make_text_block, make_response):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
    await agent.run("homeostatic_pi_controller", "reasoner/homeostatic_pi_controller.json")

    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"
