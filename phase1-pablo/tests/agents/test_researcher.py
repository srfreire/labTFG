import pytest
from unittest.mock import AsyncMock, MagicMock

from decisionlab.agents.researcher import Researcher, RESEARCHER_SYSTEM_PROMPT
from decisionlab.adapters.mock import MockWebSearch
from decisionlab.domain.models import ResearchReport


def test_system_prompt_exists():
    assert "paradigm" in RESEARCHER_SYSTEM_PROMPT.lower()


def test_researcher_has_correct_tools():
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch())
    tool_names = [t["name"] for t in r.tools]
    assert "web_search" in tool_names
    assert "launch_deep_research" in tool_names


def test_researcher_has_read_report_when_reports_dir(tmp_path):
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch(), reports_dir=tmp_path)
    tool_names = [t["name"] for t in r.tools]
    assert "read_report" in tool_names


def test_researcher_no_read_report_without_reports_dir():
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch())
    tool_names = [t["name"] for t in r.tools]
    assert "read_report" not in tool_names


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


@pytest.mark.asyncio
async def test_researcher_run_returns_research_report():
    text_block = _make_text_block(
        "# Decision-making paradigms: food\n\n## 1. Homeostatic\nDesc\n**Key authors**: X\n**Key concepts**: Y"
    )

    response = _make_response("end_turn", [text_block])

    client = AsyncMock()
    client.messages.create.return_value = response

    r = Researcher(client=client, search=MockWebSearch())
    report = await r.run("food intake behavior")

    assert isinstance(report, ResearchReport)
    assert "food" in report.summary.lower()


@pytest.mark.asyncio
async def test_researcher_accumulates_deep_reports():
    """Verify that launch_deep_research calls produce deep_reports in the result."""
    tool_block = _make_tool_use_block(
        "t1", "launch_deep_research", {"paradigm": "Homeostatic regulation"}
    )
    tool_response = _make_response("tool_use", [tool_block])

    summary_block = _make_text_block("# Paradigms\n\n## 1. Homeostatic\nDesc")
    final_response = _make_response("end_turn", [summary_block])

    client = AsyncMock()
    # Responses: Researcher call 1, DeepResearcher loop, DeepResearcher summary, Researcher call 2
    deep_text = _make_text_block("# Homeostatic — Deep research\n\nContent.")
    deep_loop_response = _make_response("end_turn", [deep_text])
    deep_summary_text = _make_text_block("**Paradigm**: Homeostatic\n**Key authors**: X")
    deep_summary_response = MagicMock()
    deep_summary_response.content = [deep_summary_text]
    client.messages.create.side_effect = [tool_response, deep_loop_response, deep_summary_response, final_response]

    r = Researcher(client=client, search=MockWebSearch())
    report = await r.run("food intake")

    assert "Homeostatic regulation" in report.deep_reports


@pytest.mark.asyncio
async def test_researcher_populates_paradigms_from_deep_reports(tmp_path):
    """Paradigms should be populated with slugs consistent with deep report filenames."""
    tool_block = _make_tool_use_block(
        "t1", "launch_deep_research", {"paradigm": "Homeostatic regulation"}
    )
    tool_response = _make_response("tool_use", [tool_block])

    summary_block = _make_text_block("# Paradigms\n\n## 1. Homeostatic\nDesc")
    final_response = _make_response("end_turn", [summary_block])

    client = AsyncMock()
    deep_text = _make_text_block("# Homeostatic — Deep research\n\nContent.")
    deep_loop_response = _make_response("end_turn", [deep_text])
    deep_summary_text = _make_text_block("**Paradigm**: Homeostatic\n**Key authors**: X")
    deep_summary_response = MagicMock()
    deep_summary_response.content = [deep_summary_text]
    client.messages.create.side_effect = [
        tool_response, deep_loop_response, deep_summary_response, final_response,
    ]

    r = Researcher(client=client, search=MockWebSearch(), reports_dir=tmp_path)
    report = await r.run("food intake")

    assert len(report.paradigms) == 1
    p = report.paradigms[0]
    assert p.name == "Homeostatic regulation"
    assert p.id == "homeostatic-regulation"  # slug must match deep/*.md filename


@pytest.mark.asyncio
async def test_researcher_clears_deep_reports_between_runs():
    """Verify that deep_reports from a previous run don't leak into a new run."""
    text_block = _make_text_block("# Summary")
    response = _make_response("end_turn", [text_block])

    client = AsyncMock()
    client.messages.create.return_value = response

    r = Researcher(client=client, search=MockWebSearch())

    r._deep_reports["stale"] = "old data"

    report = await r.run("new problem")
    assert "stale" not in report.deep_reports


@pytest.mark.asyncio
async def test_researcher_saves_summary_to_disk(tmp_path):
    text_block = _make_text_block("# Final summary")
    response = _make_response("end_turn", [text_block])

    client = AsyncMock()
    client.messages.create.return_value = response

    r = Researcher(client=client, search=MockWebSearch(), reports_dir=tmp_path)
    await r.run("test problem")

    report_file = tmp_path / "report.md"
    assert report_file.exists()
    assert "Final summary" in report_file.read_text()
