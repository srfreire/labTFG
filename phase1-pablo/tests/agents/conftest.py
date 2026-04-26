"""Shared mock helpers for agent tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class StreamCM:
    """Async context manager mimicking ``client.messages.stream(...)``.

    Used by tests whose stage agent runs through ``run_agent_loop`` at a
    max_tokens budget that trips the streaming threshold (currently the
    Researcher at 32k). Lower-budget stages still use ``messages.create``.
    """

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_final_message(self):
        return self._response


@pytest.fixture()
def streaming_client():
    """Build a client mock that wires both ``messages.stream`` and
    ``messages.create`` against a shared response queue. Whichever path the
    agent loop picks (based on max_tokens) consumes the next response.

    Pass a single response (used as ``return_value`` — repeats forever, matches
    the pre-streaming default) or a list (consumed in order).
    """
    def _make(responses):
        if not isinstance(responses, list):
            single = responses
            client = MagicMock()
            client.messages = MagicMock()
            client.messages.create = AsyncMock(return_value=single)
            client.messages.stream = MagicMock(
                side_effect=lambda **_kw: StreamCM(single)
            )
            return client

        iterator = iter(responses)
        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=lambda **_kw: next(iterator))
        client.messages.stream = MagicMock(
            side_effect=lambda **_kw: StreamCM(next(iterator))
        )
        return client
    return _make


@pytest.fixture()
def make_tool_use_block():
    def _make(id, name, input) -> MagicMock:
        block = MagicMock()
        block.type = "tool_use"
        block.id = id
        block.name = name
        block.input = input
        return block

    return _make


@pytest.fixture()
def make_text_block():
    def _make(text) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text
        return block

    return _make


@pytest.fixture()
def make_response():
    def _make(stop_reason, content) -> MagicMock:
        response = MagicMock()
        response.stop_reason = stop_reason
        response.content = content
        return response

    return _make
