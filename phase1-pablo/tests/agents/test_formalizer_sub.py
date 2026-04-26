import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from decisionlab.agents.formalizer_sub import (
    FormalizerSubAgent,
    FORMALIZER_SUB_SYSTEM_PROMPT,
)


def test_system_prompt_exists():
    assert "formulation" in FORMALIZER_SUB_SYSTEM_PROMPT.lower()


def test_system_prompt_includes_cross_formulation_comparison():
    prompt = FORMALIZER_SUB_SYSTEM_PROMPT.lower()
    assert "cross-formulation comparison" in prompt
    assert "framework" in prompt
    assert "decision mechanism" in prompt
    assert "strengths" in prompt
    assert "limitations" in prompt


def test_formalizer_sub_has_correct_tools():
    client = AsyncMock()
    agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
    tool_names = [t["name"] for t in agent.tools]
    assert "read_file" in tool_names
    assert "write_file" in tool_names


@pytest.mark.asyncio
async def test_formalizer_sub_run_returns_content(
    make_tool_use_block, make_text_block, make_response,
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

    # Mock S3 storage so read_file/write_file succeed
    s3_store: dict[str, str] = {
        "research/run-1/deep/homeostatic.md": "# Homeostatic — Deep research\n\nContent.",
    }

    async def fake_get_text(key):
        if key not in s3_store:
            raise FileNotFoundError(key)
        return s3_store[key]

    async def fake_put_text(key, content):
        s3_store[key] = content

    mock_storage = MagicMock()
    mock_storage.get_text = AsyncMock(side_effect=fake_get_text)
    mock_storage.put_text = AsyncMock(side_effect=fake_put_text)

    # Formalizer runs at 32k → streaming path in run_agent_loop.
    from tests.agents.conftest import StreamCM
    queue = iter([resp1, resp2, resp3])
    client = AsyncMock()
    client.messages.stream = MagicMock(side_effect=lambda **_kw: StreamCM(next(queue)))

    with patch("shared.storage", mock_storage):
        agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
        result = await agent.run("homeostatic")

    assert "Homeostatic" in result
    assert "Formulation 1" in result


@pytest.mark.asyncio
async def test_formalizer_sub_uses_opus_model(make_text_block, make_response, streaming_client):
    final_text = make_text_block("# Output")
    resp = make_response("end_turn", [final_text])

    client = streaming_client(resp)

    agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
    await agent.run("homeostatic")

    from decisionlab.config import SETTINGS
    # Formalizer is at 32k → uses messages.stream
    call_kwargs = client.messages.stream.call_args
    assert call_kwargs.kwargs["model"] == SETTINGS.formalizer.model
