import pytest
from unittest.mock import AsyncMock, patch

from decisionlab.agents.reasoner import Reasoner
from decisionlab.domain.models import ReasonerReport


def test_reasoner_construction():
    client = AsyncMock()
    r = Reasoner(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
        run_id="run-1",
    )
    assert r.client is client
    assert r.research_prefix == "research/run-1"
    assert r.models_prefix == "models/run-1"


@pytest.mark.asyncio
async def test_reasoner_run_collects_results():
    client = AsyncMock()
    r = Reasoner(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
    )

    async def fake_run(slug, formulation_slugs=None):
        return f"# {slug} formulation"

    with patch("decisionlab.agents.reasoner.ReasonerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await r.run(["alpha", "beta"])

    assert isinstance(report, ReasonerReport)
    assert "alpha" in report.specs
    assert "beta" in report.specs
    assert report.specs["alpha"] == "# alpha formulation"
    assert report.specs["beta"] == "# beta formulation"


@pytest.mark.asyncio
async def test_reasoner_run_discovers_paradigms_from_s3():
    client = AsyncMock()
    r = Reasoner(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
    )

    async def fake_run(slug, formulation_slugs=None):
        return f"# {slug} content"

    with (
        patch("decisionlab.agents.reasoner.ReasonerSubAgent") as MockSub,
        patch("decisionlab.agents.reasoner.shared") as mock_shared,
    ):
        mock_shared.storage.list = AsyncMock(return_value=[
            "research/run-1/formulations/paradigm-a.md",
            "research/run-1/formulations/paradigm-b.md",
        ])
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await r.run([])

    assert set(report.specs.keys()) == {"paradigm-a", "paradigm-b"}


@pytest.mark.asyncio
async def test_reasoner_run_handles_partial_failure():
    client = AsyncMock()
    r = Reasoner(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
    )

    async def fake_run(slug, formulation_slugs=None):
        if slug == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {slug} ok"

    with patch("decisionlab.agents.reasoner.ReasonerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await r.run(["good", "fail-me"])

    assert "good" in report.specs
    assert report.specs["good"] == "# good ok"
    assert "fail-me" not in report.specs


# ---- P5-003: Slug propagation tests ----


@pytest.mark.asyncio
async def test_reasoner_passes_formulation_slugs_to_sub_agent():
    """Reasoner.run passes formulation slugs from selected_formulations to sub-agents."""
    client = AsyncMock()
    r = Reasoner(
        client=client,
        research_prefix="research/run-1",
        models_prefix="models/run-1",
    )

    captured_calls = []

    async def fake_run(slug, formulation_slugs=None):
        captured_calls.append((slug, formulation_slugs))
        return f"# {slug} done"

    with patch("decisionlab.agents.reasoner.ReasonerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        selected = {
            "homeostatic": ["pi-controller", "dual-process"],
            "hedonic": ["reward-prediction"],
        }
        report = await r.run(selected)

    assert len(captured_calls) == 2
    slugs_seen = {c[0] for c in captured_calls}
    assert slugs_seen == {"homeostatic", "hedonic"}
    for slug, fslugs in captured_calls:
        if slug == "homeostatic":
            assert fslugs == ["pi-controller", "dual-process"]
        elif slug == "hedonic":
            assert fslugs == ["reward-prediction"]

    assert isinstance(report, ReasonerReport)
    assert set(report.specs.keys()) == {"homeostatic", "hedonic"}
