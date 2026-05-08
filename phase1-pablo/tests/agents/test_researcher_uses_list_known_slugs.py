"""Researcher must call list_known_slugs (not retrieve_knowledge +
markdown regex) for paradigm candidate enumeration."""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_retrieve_known_paradigms_uses_helper(monkeypatch):
    from decisionlab.agents import researcher as r_mod

    fake_helper = AsyncMock(
        return_value=[
            ("reinforcement-learning", "Value-based action selection."),
            ("prospect-theory", "Asymmetric value over gains/losses."),
        ]
    )
    monkeypatch.setattr(r_mod, "list_known_slugs", fake_helper)

    researcher = r_mod.Researcher(
        client=object(),
        search=object(),
        knowledge_tool_schema={"name": "retrieve_knowledge"},
        knowledge_tool_handler=AsyncMock(return_value=""),
    )
    slugs, text = await researcher._retrieve_known_paradigms("any topic")
    fake_helper.assert_awaited_once()
    assert slugs == ["reinforcement-learning", "prospect-theory"]
    # Synthetic deterministic block (slug + definition) — not free-form markdown.
    assert "reinforcement-learning" in text
    assert "Asymmetric value" in text


@pytest.mark.asyncio
async def test_retrieve_known_paradigms_empty_when_helper_fails(monkeypatch):
    from decisionlab.agents import researcher as r_mod

    async def boom(**_kw):
        raise RuntimeError("kg down")

    monkeypatch.setattr(r_mod, "list_known_slugs", boom)

    researcher = r_mod.Researcher(
        client=object(),
        search=object(),
        knowledge_tool_schema={"name": "retrieve_knowledge"},
        knowledge_tool_handler=AsyncMock(return_value=""),
    )
    slugs, text = await researcher._retrieve_known_paradigms("any topic")
    assert slugs == []
    assert text == ""


def test_no_more_known_slug_regex():
    """The regex parser is dead code now."""
    import inspect

    from decisionlab.agents import researcher

    src = inspect.getsource(researcher)
    assert "_KNOWN_SLUG_RE" not in src
    assert "_parse_known_slugs" not in src
