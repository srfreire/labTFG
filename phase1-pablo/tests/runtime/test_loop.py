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

    async def echo(params: dict) -> str:
        return params["msg"]

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

    async def echo(params: dict) -> str:
        return "x"

    with pytest.raises(RuntimeError, match="Max iterations"):
        await run_agent_loop(
            client=client, model="claude-sonnet-4-6", system="sys",
            tools=[], messages=[{"role": "user", "content": "hi"}],
            registry={"echo": echo}, max_iterations=3,
        )


@pytest.mark.asyncio
async def test_loop_returns_on_max_tokens_stop_reason():
    response = _make_response("max_tokens", [_make_text_block("truncated...")])

    client = AsyncMock()
    client.messages.create.return_value = response

    result = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
    )

    assert result.stop_reason == "max_tokens"
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_loop_returns_on_tool_use_with_no_tool_blocks():
    response = _make_response("tool_use", [_make_text_block("no tools here")])

    client = AsyncMock()
    client.messages.create.return_value = response

    result = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
    )

    assert result.stop_reason == "tool_use"
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_loop_propagates_api_exceptions():
    client = AsyncMock()
    client.messages.create.side_effect = RuntimeError("API connection failed")

    with pytest.raises(RuntimeError, match="API connection failed"):
        await run_agent_loop(
            client=client, model="claude-sonnet-4-6", system="sys",
            tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
        )


@pytest.mark.asyncio
async def test_loop_message_accumulation():
    """Verify the messages passed to the 2nd API call contain correct structure."""
    tool_block = _make_tool_use_block("t1", "echo", {"msg": "hi"})
    tool_response = _make_response("tool_use", [tool_block])
    final_response = _make_response("end_turn", [_make_text_block("done")])

    client = AsyncMock()
    client.messages.create.side_effect = [tool_response, final_response]

    async def echo(params: dict) -> str:
        return params["msg"]

    await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "start"}],
        registry={"echo": echo},
    )

    # Inspect the second call's messages argument
    second_call_kwargs = client.messages.create.call_args_list[1]
    messages = second_call_kwargs.kwargs["messages"]

    # Should have: original user msg, assistant with tool_use, user with tool_result
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "start"}
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"

    # tool_result should reference the tool_use_id
    tool_results = messages[2]["content"]
    assert len(tool_results) == 1
    assert tool_results[0]["tool_use_id"] == "t1"
    assert tool_results[0]["content"] == "hi"
