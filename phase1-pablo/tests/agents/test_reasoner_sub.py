import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.agents.reasoner_sub import (
    REASONER_SUB_SYSTEM_PROMPT,
    ReasonerSubAgent,
)


def test_system_prompt_exists():
    assert "json" in REASONER_SUB_SYSTEM_PROMPT.lower()
    assert "env" in REASONER_SUB_SYSTEM_PROMPT.lower()


def test_reasoner_sub_has_correct_tools():
    client = AsyncMock()
    agent = ReasonerSubAgent(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
        storage=MagicMock(),
        db=MagicMock(),
    )
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names


@pytest.mark.asyncio
async def test_reasoner_sub_run_returns_content(
    make_tool_use_block,
    make_text_block,
    make_response,
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
    read_env = make_tool_use_block("call_3", "read_file", {"path": "env_spec.json"})
    resp3 = make_response("tool_use", [read_env])

    # Step 4: LLM calls write_file with JSON spec (nested path)
    spec = {
        "formulation_id": "pi_controller",
        "paradigm": "homeostatic",
        "name": "Homeostatic PI Controller",
    }
    write_call = make_tool_use_block(
        "call_4",
        "write_file",
        {
            "path": "reasoner/homeostatic/pi_controller.json",
            "content": json.dumps(spec, indent=2),
        },
    )
    resp4 = make_response("tool_use", [write_call])

    # Step 5: LLM produces final text
    final_text = make_text_block("Produced JSON spec for pi_controller.")
    resp5 = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.side_effect = [resp1, resp2, resp3, resp4, resp5]

    agent = ReasonerSubAgent(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
        storage=MagicMock(),
        db=MagicMock(),
    )
    result = await agent.run("homeostatic")

    assert "pi_controller" in result


@pytest.mark.asyncio
async def test_reasoner_sub_uses_opus_model(make_text_block, make_response):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = ReasonerSubAgent(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
        storage=MagicMock(),
        db=MagicMock(),
    )
    await agent.run("homeostatic")

    from decisionlab.config import SETTINGS

    call_kwargs = client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == SETTINGS.reasoner.model


# ---- P5-003: Slug-based path tests ----


@pytest.mark.asyncio
async def test_reasoner_sub_includes_formulation_slugs_in_message(
    make_text_block,
    make_response,
):
    """When formulation_slugs are passed, they appear in the user message."""
    final_text = make_text_block("Done")
    resp = make_response("end_turn", [final_text])

    client = AsyncMock()
    client.messages.create.return_value = resp

    agent = ReasonerSubAgent(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
        storage=MagicMock(),
        db=MagicMock(),
    )
    await agent.run("homeostatic", formulation_slugs=["pi-controller", "dual-process"])

    call_kwargs = client.messages.create.call_args
    messages = call_kwargs.kwargs["messages"]
    user_msg = messages[0]["content"]
    assert "pi-controller" in user_msg
    assert "dual-process" in user_msg
    # Path instruction uses paradigm slug in path
    assert "reasoner/homeostatic/" in user_msg


def test_system_prompt_uses_paradigm_slug_paths():
    """System prompt should instruct writing to reasoner/{paradigm_slug}/{formulation_slug}.json."""
    assert (
        "reasoner/{paradigm_slug}/{formulation_slug}.json" in REASONER_SUB_SYSTEM_PROMPT
    )


def test_system_prompt_does_not_reference_formulation_ids():
    """System prompt should NOT reference 'Formulation IDs' section."""
    assert "Formulation IDs" not in REASONER_SUB_SYSTEM_PROMPT
    assert "formulation_id}.json" not in REASONER_SUB_SYSTEM_PROMPT


# ---- P4-001: Validation tests ----


def test_system_prompt_contains_validation_step():
    """System prompt must include a validation phase before spec generation."""
    prompt_lower = REASONER_SUB_SYSTEM_PROMPT.lower()
    assert "validation" in prompt_lower
    assert "invalid" in prompt_lower
    assert "problems" in prompt_lower


def test_system_prompt_lists_validation_checks():
    """System prompt must list the specific coherence checks."""
    assert "undefined_variable" in REASONER_SUB_SYSTEM_PROMPT
    assert "circular_dependency" in REASONER_SUB_SYSTEM_PROMPT
    assert "invalid_reference" in REASONER_SUB_SYSTEM_PROMPT
    assert "unreasonable_default" in REASONER_SUB_SYSTEM_PROMPT
    assert "inconsistent_mapping" in REASONER_SUB_SYSTEM_PROMPT
