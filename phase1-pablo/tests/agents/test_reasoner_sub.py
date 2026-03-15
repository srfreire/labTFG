import json

import pytest
from unittest.mock import AsyncMock

from decisionlab.agents.reasoner_sub import (
    ReasonerSubAgent,
    REASONER_SUB_SYSTEM_PROMPT,
)


def test_system_prompt_exists():
    assert "json" in REASONER_SUB_SYSTEM_PROMPT.lower()
    assert "env" in REASONER_SUB_SYSTEM_PROMPT.lower()


def test_reasoner_sub_has_correct_tools(tmp_path):
    client = AsyncMock()
    agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names


@pytest.mark.asyncio
async def test_reasoner_sub_run_returns_content(
    tmp_path, make_tool_use_block, make_text_block, make_response,
):
    # Step 1: LLM calls read_file for deep report
    read_deep = make_tool_use_block(
        "call_1", "read_file", {"path": "deep/homeostatic.md"}
    )
    resp1 = make_response("tool_use", [read_deep])

    # Step 2: LLM calls read_file for formulations
    read_form = make_tool_use_block(
        "call_2", "read_file", {"path": "formulations/homeostatic.md"}
    )
    resp2 = make_response("tool_use", [read_form])

    # Step 3: LLM calls read_file for env_spec
    read_env = make_tool_use_block(
        "call_3", "read_file", {"path": "env_spec.json"}
    )
    resp3 = make_response("tool_use", [read_env])

    # Step 4: LLM calls write_file with JSON spec
    spec = {
        "formulation_id": "homeostatic_pi_controller",
        "paradigm": "homeostatic",
        "name": "Homeostatic PI Controller",
    }
    write_call = make_tool_use_block(
        "call_4",
        "write_file",
        {
            "path": "reasoner/homeostatic_pi_controller.json",
            "content": json.dumps(spec, indent=2),
        },
    )
    resp4 = make_response("tool_use", [write_call])

    # Step 5: LLM produces final text
    final_text = make_text_block(
        "Produced JSON spec for homeostatic_pi_controller."
    )
    resp5 = make_response("end_turn", [final_text])

    # Prepare fixture files so read_file succeeds
    deep_dir = tmp_path / "deep"
    deep_dir.mkdir(parents=True)
    (deep_dir / "homeostatic.md").write_text(
        "# Homeostatic — Deep research\n\nContent."
    )

    form_dir = tmp_path / "formulations"
    form_dir.mkdir(parents=True)
    (form_dir / "homeostatic.md").write_text(
        "# Homeostatic — Mathematical formulations\n\n## Formulation 1: PI Controller"
    )

    (tmp_path / "env_spec.json").write_text(
        json.dumps({"actions": ["up", "down", "left", "right", "stay", "eat"]})
    )

    client = AsyncMock()
    client.messages.create.side_effect = [resp1, resp2, resp3, resp4, resp5]

    agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
    result = await agent.run("homeostatic")

    assert "homeostatic_pi_controller" in result


@pytest.mark.asyncio
async def test_reasoner_sub_uses_opus_model(tmp_path, make_text_block, make_response):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
    await agent.run("homeostatic")

    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-opus-4-6"
