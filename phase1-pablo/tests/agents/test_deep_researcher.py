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
async def test_deep_researcher_run_returns_summary():
    """DeepResearcher returns a concise summary, not the full report."""
    # First call: the agentic loop (returns full report)
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Homeostatic — Deep research\n\n## Foundations\nContent."

    loop_response = MagicMock()
    loop_response.stop_reason = "end_turn"
    loop_response.content = [text_block]

    # Second call: the summary extraction
    summary_block = MagicMock()
    summary_block.type = "text"
    summary_block.text = "**Paradigm**: Homeostatic\n**Key authors**: Jacquier"

    summary_response = MagicMock()
    summary_response.content = [summary_block]

    client = AsyncMock()
    client.messages.create.side_effect = [loop_response, summary_response]

    dr = DeepResearcher(client=client, search=MockWebSearch())
    result = await dr.run("Homeostatic regulation")

    assert "Homeostatic" in result
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_deep_researcher_saves_report_to_disk(tmp_path):
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Homeostatic — Deep research\n\nFull content."

    loop_response = MagicMock()
    loop_response.stop_reason = "end_turn"
    loop_response.content = [text_block]

    summary_block = MagicMock()
    summary_block.type = "text"
    summary_block.text = "**Paradigm**: Homeostatic"

    summary_response = MagicMock()
    summary_response.content = [summary_block]

    client = AsyncMock()
    client.messages.create.side_effect = [loop_response, summary_response]

    dr = DeepResearcher(client=client, search=MockWebSearch(), reports_dir=tmp_path)
    await dr.run("Homeostatic regulation")

    report_file = tmp_path / "deep" / "homeostatic-regulation.md"
    assert report_file.exists()
    assert "Full content" in report_file.read_text()
