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


class _StreamCM:
    """Async context manager mimicking ``client.messages.stream(...)``."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_final_message(self):
        return self._response


def _client_with(responses):
    """Build a client whose ``messages.stream(...)`` returns the given responses
    in order. ``responses`` is a single response or a list."""
    if not isinstance(responses, list):
        responses = [responses]
    iterator = iter(responses)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(
        side_effect=lambda **_kw: _StreamCM(next(iterator))
    )
    return client


def _client_with_exception(exc):
    """Build a client whose ``messages.stream(...)`` raises on entry."""
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.stream = MagicMock(side_effect=exc)
    return client


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
async def test_loop_raises_on_max_tokens_stop_reason():
    """max_tokens means the response was truncated mid-emit. Returning it
    as-is silently corrupts downstream stages (e.g. Researcher → report.md
    → memory extraction). Raise loud instead."""
    response = _make_response("max_tokens", [_make_text_block("truncated...")])
    response.usage = MagicMock(output_tokens=4096)

    client = AsyncMock()
    client.messages.create.return_value = response

    with pytest.raises(RuntimeError, match="hit max_tokens"):
        await run_agent_loop(
            client=client, model="claude-sonnet-4-6", system="sys",
            tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
            max_tokens=4096,
        )

    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_loop_warns_and_returns_on_other_unexpected_stop_reasons():
    """Non-max_tokens unexpected reasons (e.g. refusal, content_filter) are
    not truncations — keep the lenient 'warn + return' fallback for those."""
    response = _make_response("refusal", [_make_text_block("...")])

    client = AsyncMock()
    client.messages.create.return_value = response

    result = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
    )

    assert result.stop_reason == "refusal"
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
async def test_loop_streams_when_max_tokens_exceeds_threshold():
    """At Researcher's 32k budget the SDK's non-streaming guard would refuse
    the call, so the loop has to switch to ``messages.stream``."""
    response = _make_response("end_turn", [_make_text_block("done")])
    client = _client_with(response)

    result = await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
        max_tokens=32768,
    )

    assert result.stop_reason == "end_turn"
    assert client.messages.stream.call_count == 1


@pytest.mark.asyncio
async def test_loop_uses_create_below_streaming_threshold():
    """Below the streaming threshold, the loop uses ``messages.create`` so
    existing low-budget tests (default 4096) keep working."""
    response = _make_response("end_turn", [_make_text_block("done")])
    client = AsyncMock()
    client.messages.create.return_value = response

    await run_agent_loop(
        client=client, model="claude-sonnet-4-6", system="sys",
        tools=[], messages=[{"role": "user", "content": "hi"}], registry={},
        max_tokens=16384,
    )

    assert client.messages.create.call_count == 1


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
