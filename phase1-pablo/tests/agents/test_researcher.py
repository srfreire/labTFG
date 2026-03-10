import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.agents.researcher import Researcher, RESEARCHER_SYSTEM_PROMPT
from decisionlab.adapters.mock import MockWebSearch, MockPaperSearch
from decisionlab.domain.models import ResearchReport


def test_system_prompt_exists():
    assert "breadth-first" in RESEARCHER_SYSTEM_PROMPT.lower()


def test_researcher_has_correct_tools():
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    tool_names = [t["name"] for t in r.tools]
    assert "web_search" in tool_names
    assert "search_papers" in tool_names
    assert "launch_deep_research" in tool_names
    assert "fetch_paper" not in tool_names


@pytest.mark.asyncio
async def test_researcher_run_returns_research_report():
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Decision-making paradigms: food\n\n## 1. Homeostatic\nDesc\n**Key authors**: X\n**Key concepts**: Y"

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]

    client = AsyncMock()
    client.messages.create.return_value = response

    r = Researcher(client=client, search=MockWebSearch(), papers=MockPaperSearch())
    report = await r.run("food intake behavior")

    assert isinstance(report, ResearchReport)
    assert "food" in report.summary.lower()
