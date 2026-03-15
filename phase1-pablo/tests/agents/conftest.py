"""Shared mock helpers for agent tests."""

from unittest.mock import MagicMock

import pytest


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
