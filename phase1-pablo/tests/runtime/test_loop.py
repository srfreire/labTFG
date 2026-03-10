import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.runtime.loop import run_agent_loop


def _make_tool_use_block(id: str, name: str, input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input
    return block


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_response(stop_reason: str, content: list):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    return resp


@pytest.mark.asyncio
async def test_loop_returns_immediately_on_end_turn():
    client = AsyncMock()
    client.messages.create.return_value = _make_response(
        "end_turn", [_make_text_block("done")]
    )

    response = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
    )

    assert response.stop_reason == "end_turn"
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_loop_dispatches_tool_and_continues():
    tool_response = _make_response(
        "tool_use", [_make_tool_use_block("t1", "echo", {"msg": "hello"})]
    )
    final_response = _make_response("end_turn", [_make_text_block("result")])

    client = AsyncMock()
    client.messages.create.side_effect = [tool_response, final_response]

    async def echo(input: dict) -> str:
        return input["msg"]

    response = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}],
        registry={"echo": echo},
    )

    assert response.stop_reason == "end_turn"
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_loop_respects_max_iterations():
    tool_response = _make_response(
        "tool_use", [_make_tool_use_block("t1", "echo", {"msg": "x"})]
    )

    client = AsyncMock()
    client.messages.create.return_value = tool_response

    async def echo(input: dict) -> str:
        return "x"

    with pytest.raises(RuntimeError, match="Max iterations"):
        await run_agent_loop(
            client=client, model="claude-sonnet-4-6", system="sys",
            tools=[], messages=[{"role": "user", "content": "hi"}],
            registry={"echo": echo}, max_iterations=3,
        )
