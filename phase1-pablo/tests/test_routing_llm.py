"""Tests for classify_feedback in routing_llm.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.domain.models import RerunRequest
from decisionlab.routing_llm import classify_feedback


def _make_text_response(text: str) -> MagicMock:
    """Build a mock Anthropic response with a single text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class TestClassifyFeedback:
    async def test_classify_feedback_happy_path(self):
        client = AsyncMock()
        client.messages.create.return_value = _make_text_response(
            '{"target": "builder", "paradigm": "homeostatic", "reason": "test failure"}'
        )

        result = await classify_feedback(
            client=client,
            feedback="The tests are failing with import errors",
            paradigms=["homeostatic", "hedonic"],
        )

        assert isinstance(result, RerunRequest)
        assert result.target == "builder"
        assert result.paradigm == "homeostatic"
        # feedback should be the user's text, not the LLM's reason
        assert result.feedback == "The tests are failing with import errors"

    async def test_classify_feedback_retries_on_bad_json(self):
        client = AsyncMock()
        client.messages.create.side_effect = [
            _make_text_response("not json at all!!!"),
            _make_text_response(
                '{"target": "reasoner", "paradigm": "hedonic", "reason": "bad spec"}'
            ),
        ]

        result = await classify_feedback(
            client=client,
            feedback="The spec is wrong",
            paradigms=["hedonic"],
        )

        assert result.target == "reasoner"
        assert result.paradigm == "hedonic"
        assert client.messages.create.call_count == 2

    async def test_classify_feedback_raises_after_two_failures(self):
        client = AsyncMock()
        client.messages.create.side_effect = [
            _make_text_response("garbage"),
            _make_text_response("still garbage"),
        ]

        with pytest.raises(
            ValueError, match="could not parse Haiku response after 2 attempts"
        ):
            await classify_feedback(
                client=client,
                feedback="something is wrong",
                paradigms=["homeostatic"],
            )

    async def test_classify_feedback_invalid_target(self):
        client = AsyncMock()
        client.messages.create.side_effect = [
            _make_text_response(
                '{"target": "unknown_agent", "paradigm": "homeostatic", "reason": "x"}'
            ),
            _make_text_response(
                '{"target": "builder", "paradigm": "homeostatic", "reason": "fixed"}'
            ),
        ]

        result = await classify_feedback(
            client=client,
            feedback="some issue",
            paradigms=["homeostatic"],
        )

        assert result.target == "builder"
        assert client.messages.create.call_count == 2

    async def test_classify_feedback_stores_user_feedback(self):
        client = AsyncMock()
        client.messages.create.return_value = _make_text_response(
            '{"target": "formalizer", "paradigm": "integrated", "reason": "LLM reason text"}'
        )

        user_text = "The equations are completely wrong"
        result = await classify_feedback(
            client=client,
            feedback=user_text,
            paradigms=["integrated"],
        )

        assert result.feedback == user_text
        assert result.feedback != "LLM reason text"

    async def test_classify_feedback_strips_markdown_fences(self):
        client = AsyncMock()
        client.messages.create.return_value = _make_text_response(
            '```json\n{"target": "builder", "paradigm": "homeostatic", "reason": "test failure"}\n```'
        )

        result = await classify_feedback(
            client=client,
            feedback="tests crash",
            paradigms=["homeostatic"],
        )

        assert result.target == "builder"
        assert result.paradigm == "homeostatic"
        assert client.messages.create.call_count == 1  # no retry needed

    async def test_classify_feedback_builds_context(self):
        client = AsyncMock()
        client.messages.create.return_value = _make_text_response(
            '{"target": "builder", "paradigm": "homeostatic", "reason": "ok"}'
        )

        await classify_feedback(
            client=client,
            feedback="fix the code",
            paradigms=["homeostatic", "hedonic"],
            spec_content="some spec data",
            build_output="build log here",
        )

        call_args = client.messages.create.call_args
        user_msg = call_args.kwargs["messages"][0]["content"]

        assert "homeostatic" in user_msg
        assert "hedonic" in user_msg
        assert "some spec data" in user_msg
        assert "build log here" in user_msg
        assert "fix the code" in user_msg
