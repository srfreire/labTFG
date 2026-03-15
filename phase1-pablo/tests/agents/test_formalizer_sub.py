import pytest
from unittest.mock import AsyncMock

from decisionlab.agents.formalizer_sub import (
    FormalizerSubAgent,
    FORMALIZER_SUB_SYSTEM_PROMPT,
)


def test_system_prompt_exists():
    assert "formulation" in FORMALIZER_SUB_SYSTEM_PROMPT.lower()


def test_formalizer_sub_has_correct_tools(tmp_path):
    client = AsyncMock()
    agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names


@pytest.mark.asyncio
async def test_formalizer_sub_run_returns_content(
    tmp_path, make_tool_use_block, make_text_block, make_response,
):
    # Step 1: LLM calls read_file
    read_call = make_tool_use_block(
        "call_1", "read_file", {"path": "deep/homeostatic.md"}
    )
    resp1 = make_response("tool_use", [read_call])

    # Step 2: LLM calls write_file
    write_call = make_tool_use_block(
        "call_2",
        "write_file",
        {
            "path": "formulations/homeostatic.md",
            "content": "# Homeostatic — Mathematical formulations\n\n## Formulation 1",
        },
    )
    resp2 = make_response("tool_use", [write_call])

    # Step 3: LLM produces final text
    final_text = make_text_block(
        "# Homeostatic — Mathematical formulations\n\n## Formulation 1: Energy model"
    )
    resp3 = make_response("end_turn", [final_text])

    # Prepare deep report so read_file succeeds
    deep_dir = tmp_path / "deep"
    deep_dir.mkdir(parents=True)
    (deep_dir / "homeostatic.md").write_text("# Homeostatic — Deep research\n\nContent.")

    client = AsyncMock()
    client.messages.create.side_effect = [resp1, resp2, resp3]

    agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
    result = await agent.run("homeostatic")

    assert "Homeostatic" in result
    assert "Formulation 1" in result


@pytest.mark.asyncio
async def test_formalizer_sub_uses_opus_model(tmp_path, make_text_block, make_response):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
    await agent.run("homeostatic")

    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-opus-4-6"
