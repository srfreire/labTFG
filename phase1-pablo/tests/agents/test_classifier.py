"""Tests for the umbrella classifier (Issue 4 of fix-5-issues)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.agents.classifier import (
    UmbrellaDecision,
    _build_decision_model,
    _format_known,
    classify_umbrella,
)


def test_format_known_empty_returns_placeholder():
    out = _format_known([])
    assert "no canonical umbrellas" in out


def test_format_known_lists_slugs_and_definitions():
    out = _format_known(
        [
            {"slug": "rl", "name": "RL", "definition": "Reward-driven learning."},
            {"slug": "pt", "name": "PT", "definition": "Reference-dependent risk."},
        ]
    )
    assert "**rl**" in out and "Reward-driven" in out
    assert "**pt**" in out and "Reference-dependent" in out


def test_decision_model_enforces_known_slugs():
    """The constrained model rejects unknown slugs at the Pydantic level."""
    Model = _build_decision_model(["reinforcement-learning", "prospect-theory"])

    valid = Model(
        chosen_slug="reinforcement-learning",
        chosen_name="RL",
        definition="x",
        rationale="y",
        confidence=0.9,
    )
    assert valid.chosen_slug == "reinforcement-learning"

    new = Model(
        chosen_slug="__NEW__",
        chosen_name="Novel",
        definition="x",
        rationale="y",
        confidence=0.4,
    )
    assert new.chosen_slug == "__NEW__"

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Model(
            chosen_slug="some-other-slug",
            chosen_name="x",
            definition="y",
            rationale="z",
            confidence=0.5,
        )


def _tool_use_response(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_UmbrellaDecision"
    block.input = payload
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.usage = None
    return resp


@pytest.mark.asyncio
async def test_classify_umbrella_routes_to_known_slug():
    """Given known umbrellas, a classifier hit returns the chosen slug."""
    response = _tool_use_response(
        {
            "chosen_slug": "reinforcement-learning",
            "chosen_name": "Reinforcement learning",
            "definition": "Reward-driven action-value learning.",
            "rationale": "Q-learning is RL.",
            "confidence": 0.95,
        }
    )
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    decision = await classify_umbrella(
        "Q-learning agent that picks actions to maximize reward",
        client=client,
        known_umbrellas=[
            {
                "slug": "reinforcement-learning",
                "name": "Reinforcement learning",
                "definition": "Reward-driven learning.",
            },
        ],
    )
    assert isinstance(decision, UmbrellaDecision)
    assert decision.chosen_slug == "reinforcement-learning"
    assert decision.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_umbrella_falls_back_to_new_when_no_match():
    """A genuinely-novel problem returns __NEW__ — Researcher behaves as today."""
    response = _tool_use_response(
        {
            "chosen_slug": "__NEW__",
            "chosen_name": "Novel paradigm",
            "definition": "Something new.",
            "rationale": "No umbrella covers this mechanism.",
            "confidence": 0.3,
        }
    )
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    decision = await classify_umbrella(
        "an unprecedented paradigm",
        client=client,
        known_umbrellas=[
            {"slug": "rl", "name": "RL", "definition": "x"},
        ],
    )
    assert decision.chosen_slug == "__NEW__"
