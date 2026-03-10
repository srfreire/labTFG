import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.agents.deep_researcher import DeepResearcher, DEEP_RESEARCHER_SYSTEM_PROMPT
from decisionlab.adapters.mock import MockWebSearch


def test_system_prompt_exists():
    assert "paradigm" in DEEP_RESEARCHER_SYSTEM_PROMPT.lower()


def test_deep_researcher_has_correct_tools():
    client = AsyncMock()
    dr = DeepResearcher(client=client, search=MockWebSearch())
    tool_names = [t["name"] for t in dr.tools]
    assert "web_search" in tool_names
    assert "launch_deep_research" not in tool_names


@pytest.mark.asyncio
async def test_deep_researcher_run_returns_markdown():
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Homeostatic — Deep research\n\n## Foundations\nContent."

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = AsyncMock()
    client.messages.create.return_value = response

    dr = DeepResearcher(client=client, search=MockWebSearch())
    result = await dr.run("Homeostatic regulation")

    assert "Homeostatic" in result
    assert client.messages.create.called
