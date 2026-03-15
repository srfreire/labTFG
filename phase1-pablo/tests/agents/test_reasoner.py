import pytest
from unittest.mock import AsyncMock, patch

from decisionlab.agents.reasoner import Reasoner
from decisionlab.domain.models import ReasonerReport


def test_reasoner_construction(tmp_path):
    client = AsyncMock()
    r = Reasoner(client=client, reports_dir=tmp_path)
    assert r.client is client
    assert r.reports_dir is tmp_path


@pytest.mark.asyncio
async def test_reasoner_run_collects_results(tmp_path):
    client = AsyncMock()
    r = Reasoner(client=client, reports_dir=tmp_path)

    async def fake_run(slug):
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
async def test_reasoner_run_discovers_paradigms_from_disk(tmp_path):
    formulations_dir = tmp_path / "formulations"
    formulations_dir.mkdir()
    (formulations_dir / "paradigm-a.md").write_text("Report A")
    (formulations_dir / "paradigm-b.md").write_text("Report B")

    client = AsyncMock()
    r = Reasoner(client=client, reports_dir=tmp_path)

    async def fake_run(slug):
        return f"# {slug} content"

    with patch("decisionlab.agents.reasoner.ReasonerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await r.run([])

    assert set(report.specs.keys()) == {"paradigm-a", "paradigm-b"}


@pytest.mark.asyncio
async def test_reasoner_run_handles_partial_failure(tmp_path):
    client = AsyncMock()
    r = Reasoner(client=client, reports_dir=tmp_path)

    call_count = 0

    async def fake_run(slug):
        nonlocal call_count
        call_count += 1
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
