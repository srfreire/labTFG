from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.agents.researcher import RESEARCHER_SYSTEM_PROMPT, Researcher
from decisionlab.domain.models import ResearchReport


def test_system_prompt_exists():
    assert "paradigm" in RESEARCHER_SYSTEM_PROMPT.lower()


def test_system_prompt_has_cross_paradigm_matrix_instructions():
    """P2-005: Prompt must instruct the matrix format for cross-paradigm table."""
    prompt = RESEARCHER_SYSTEM_PROMPT.lower()
    # Must reference cross-paradigm interaction map
    assert "cross-paradigm interaction map" in prompt
    # Must instruct matrix format with zones as columns
    assert "primary locus" in prompt
    # Must reference ✓/✗ cell markers
    assert "✓" in RESEARCHER_SYSTEM_PROMPT and "✗" in RESEARCHER_SYSTEM_PROMPT


def test_researcher_has_correct_tools():
    client = AsyncMock()
    r = Researcher(client=client, search=MockWebSearch())
    tool_names = [t["name"] for t in r.tools]
    assert "web_search" in tool_names
    assert "launch_deep_research" in tool_names


def test_researcher_has_read_report_when_run_id():
    client = AsyncMock()
    r = Researcher(
        client=client,
        search=MockWebSearch(),
        run_id="run-1",
        storage=MagicMock(),
        db=MagicMock(),
    )
    tool_names = [t["name"] for t in r.tools]
    assert "read_report" in tool_names


def test_researcher_no_read_report_without_run_id():
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
async def test_researcher_run_returns_research_report(streaming_client):
    text_block = _make_text_block(
        "# Decision-making paradigms: food\n\n## 1. Homeostatic\nDesc\n**Key authors**: X\n**Key concepts**: Y"
    )

    response = _make_response("end_turn", [text_block])

    client = streaming_client(response)

    r = Researcher(client=client, search=MockWebSearch())
    report = await r.run("food intake behavior")

    assert isinstance(report, ResearchReport)
    assert "food" in report.summary.lower()


@pytest.mark.asyncio
async def test_researcher_accumulates_deep_reports(streaming_client):
    """Verify that launch_deep_research calls produce deep_reports in the result."""
    tool_block = _make_tool_use_block(
        "t1", "launch_deep_research", {"paradigm": "Homeostatic regulation"}
    )
    tool_response = _make_response("tool_use", [tool_block])

    summary_block = _make_text_block("# Paradigms\n\n## 1. Homeostatic\nDesc")
    final_response = _make_response("end_turn", [summary_block])

    deep_text = _make_text_block("# Homeostatic — Deep research\n\nContent.")
    deep_loop_response = _make_response("end_turn", [deep_text])
    deep_summary_text = _make_text_block(
        "**Paradigm**: Homeostatic\n**Key authors**: X"
    )
    deep_summary_response = MagicMock()
    deep_summary_response.content = [deep_summary_text]

    client = streaming_client(
        [tool_response, deep_loop_response, deep_summary_response, final_response]
    )

    r = Researcher(client=client, search=MockWebSearch())
    report = await r.run("food intake")

    assert "Homeostatic regulation" in report.deep_reports


@pytest.mark.asyncio
async def test_researcher_populates_paradigms_from_deep_reports(streaming_client):
    """Paradigms should be populated with slugs consistent with deep report filenames."""
    tool_block = _make_tool_use_block(
        "t1", "launch_deep_research", {"paradigm": "Homeostatic regulation"}
    )
    tool_response = _make_response("tool_use", [tool_block])

    summary_block = _make_text_block("# Paradigms\n\n## 1. Homeostatic\nDesc")
    final_response = _make_response("end_turn", [summary_block])

    deep_text = _make_text_block("# Homeostatic — Deep research\n\nContent.")
    deep_loop_response = _make_response("end_turn", [deep_text])
    deep_summary_text = _make_text_block(
        "**Paradigm**: Homeostatic\n**Key authors**: X"
    )
    deep_summary_response = MagicMock()
    deep_summary_response.content = [deep_summary_text]

    client = streaming_client(
        [tool_response, deep_loop_response, deep_summary_response, final_response]
    )

    with (
        patch(
            "decisionlab.agents.deep_researcher.save_deep_report",
            new_callable=AsyncMock,
        ),
        patch(
            "decisionlab.agents.researcher.save_summary_report", new_callable=AsyncMock
        ),
    ):
        r = Researcher(client=client, search=MockWebSearch(), run_id="run-1")
        report = await r.run("food intake")

    assert len(report.paradigms) == 1
    p = report.paradigms[0]
    assert p.name == "Homeostatic regulation"
    assert p.id == "homeostatic-regulation"  # slug must match deep/*.md filename


@pytest.mark.asyncio
async def test_researcher_clears_deep_reports_between_runs(streaming_client):
    """Verify that deep_reports from a previous run don't leak into a new run."""
    text_block = _make_text_block("# Summary")
    response = _make_response("end_turn", [text_block])

    client = streaming_client(response)

    r = Researcher(client=client, search=MockWebSearch())

    r._deep_reports["stale"] = "old data"

    report = await r.run("new problem")
    assert "stale" not in report.deep_reports


@pytest.mark.asyncio
async def test_researcher_saves_summary_to_s3(streaming_client):
    text_block = _make_text_block("# Final summary")
    response = _make_response("end_turn", [text_block])

    client = streaming_client(response)

    storage = MagicMock()
    db = MagicMock()
    with patch(
        "decisionlab.agents.researcher.save_summary_report", new_callable=AsyncMock
    ) as mock_save:
        r = Researcher(
            client=client,
            search=MockWebSearch(),
            run_id="run-1",
            storage=storage,
            db=db,
        )
        await r.run("test problem")
        mock_save.assert_called_once_with(
            "run-1", "# Final summary", storage=storage, db=db
        )


@pytest.mark.asyncio
async def test_researcher_anchor_umbrella_added_to_known_slugs(streaming_client):
    """Passing anchor_umbrella with a non-__NEW__ slug ensures it appears in
    the candidate enum so the emission can reuse it without crossing the
    Literal-constraint barrier."""
    from decisionlab.agents.classifier import UmbrellaDecision

    text_block = _make_text_block("# Final")
    response = _make_response("end_turn", [text_block])
    client = streaming_client(response)

    anchor = UmbrellaDecision(
        chosen_slug="reinforcement-learning",
        chosen_name="Reinforcement learning",
        definition="Agents learn from reward feedback.",
        rationale="Q-learning is RL.",
        confidence=0.95,
    )

    captured = {}

    async def _fake_emit(*, problem, summary, known_slugs, retrieval_text, **_):
        captured["known_slugs"] = list(known_slugs)
        from decisionlab.domain.models import Paradigm

        return [
            Paradigm(
                id="reinforcement-learning",
                name="Reinforcement learning",
                description="x",
            )
        ]

    r = Researcher(client=client, search=MockWebSearch())
    with patch.object(r, "_emit_structured", side_effect=_fake_emit):
        await r.run(
            "Q-learning agent picks actions to maximize reward", anchor_umbrella=anchor
        )

    assert "reinforcement-learning" in captured["known_slugs"]
    assert captured["known_slugs"][0] == "reinforcement-learning"


@pytest.mark.asyncio
async def test_researcher_anchor_umbrella_new_does_not_inject(streaming_client):
    """Anchor with chosen_slug='__NEW__' is treated as no-anchor — the
    Researcher behaves as it did pre-classifier."""
    from decisionlab.agents.classifier import UmbrellaDecision

    text_block = _make_text_block("# Final")
    response = _make_response("end_turn", [text_block])
    client = streaming_client(response)

    anchor = UmbrellaDecision(
        chosen_slug="__NEW__",
        chosen_name="Novel",
        definition="Something new.",
        rationale="No known umbrella fits.",
        confidence=0.4,
    )

    captured = {}

    async def _fake_emit(*, problem, summary, known_slugs, retrieval_text, **_):
        captured["known_slugs"] = list(known_slugs)
        return []

    r = Researcher(client=client, search=MockWebSearch())
    with patch.object(r, "_emit_structured", side_effect=_fake_emit):
        await r.run("a genuinely novel paradigm", anchor_umbrella=anchor)

    # Empty known_slugs — anchor was __NEW__ so nothing to inject.
    assert captured["known_slugs"] == []
