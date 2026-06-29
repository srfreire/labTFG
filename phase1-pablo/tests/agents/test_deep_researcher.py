from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.agents.deep_researcher import (
    DEEP_RESEARCHER_SYSTEM_PROMPT,
    DeepResearcher,
)


def test_system_prompt_exists():
    assert "paradigm" in DEEP_RESEARCHER_SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_both_tools():
    assert "search_papers" in DEEP_RESEARCHER_SYSTEM_PROMPT
    assert "web_search" in DEEP_RESEARCHER_SYSTEM_PROMPT


def test_deep_researcher_has_correct_tools():
    client = AsyncMock()
    dr = DeepResearcher(client=client, search=MockWebSearch())
    tool_names = [t["name"] for t in dr.tools]
    assert "web_search" in tool_names
    assert "search_papers" in tool_names
    assert "launch_deep_research" not in tool_names


def test_deep_researcher_registry_has_search_papers():
    client = AsyncMock()
    dr = DeepResearcher(client=client, search=MockWebSearch())
    assert "search_papers" in dr.registry
    assert "web_search" in dr.registry


def test_deep_researcher_accepts_custom_paper_search():
    client = AsyncMock()
    paper_search = AsyncMock(return_value="corpus-only")

    dr = DeepResearcher(
        client=client,
        search=MockWebSearch(),
        paper_search=paper_search,
    )

    assert dr.registry["search_papers"] is paper_search


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
    client.messages.create = AsyncMock(side_effect=[loop_response, summary_response])

    dr = DeepResearcher(client=client, search=MockWebSearch())
    result = await dr.run("Homeostatic regulation")

    assert "Homeostatic" in result
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_deep_researcher_saves_report_to_s3():
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
    client.messages.create = AsyncMock(side_effect=[loop_response, summary_response])

    storage = MagicMock()
    db = MagicMock()
    dr = DeepResearcher(
        client=client,
        search=MockWebSearch(),
        run_id="run-1",
        storage=storage,
        db=db,
    )

    with patch(
        "decisionlab.agents.deep_researcher.save_deep_report", new_callable=AsyncMock
    ) as mock_save:
        await dr.run("Homeostatic regulation")
        mock_save.assert_called_once_with(
            "run-1",
            "Homeostatic regulation",
            "# Homeostatic — Deep research\n\nFull content.",
            storage=storage,
            db=db,
        )


@pytest.mark.asyncio
async def test_deep_researcher_empty_report_returns_early():
    """When agent loop returns empty text, return early without calling haiku."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "   "

    loop_response = MagicMock()
    loop_response.stop_reason = "end_turn"
    loop_response.content = [text_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=loop_response)

    dr = DeepResearcher(client=client, search=MockWebSearch())
    result = await dr.run("Empty paradigm")

    assert "No results found" in result
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_deep_researcher_empty_report_no_s3_save():
    """When agent loop returns empty text, nothing is saved to S3."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = ""

    loop_response = MagicMock()
    loop_response.stop_reason = "end_turn"
    loop_response.content = [text_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=loop_response)

    dr = DeepResearcher(client=client, search=MockWebSearch(), run_id="run-1")

    with patch(
        "decisionlab.agents.deep_researcher.save_deep_report", new_callable=AsyncMock
    ) as mock_save:
        await dr.run("Empty paradigm")
        mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_deep_researcher_summary_fallback_on_api_error():
    """When haiku summary call fails, falls back to truncated report."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "# Paradigm report\n\nSome content here."

    loop_response = MagicMock()
    loop_response.stop_reason = "end_turn"
    loop_response.content = [text_block]

    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=[loop_response, Exception("API error")]
    )

    dr = DeepResearcher(client=client, search=MockWebSearch())
    result = await dr.run("Failing paradigm")

    assert "Paradigm report" in result
    assert "[Full report saved to S3]" in result
