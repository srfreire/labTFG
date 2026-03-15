import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from decisionlab.agents.formalizer import Formalizer
from decisionlab.domain.models import FormalizationReport


def test_formalizer_construction(tmp_path):
    client = AsyncMock()
    f = Formalizer(client=client, reports_dir=tmp_path)
    assert f.client is client
    assert f.reports_dir is tmp_path


@pytest.mark.asyncio
async def test_formalizer_run_collects_results(tmp_path):
    client = AsyncMock()
    f = Formalizer(client=client, reports_dir=tmp_path)

    async def fake_run(slug):
        return f"# {slug} formulation"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run(["alpha", "beta"])

    assert isinstance(report, FormalizationReport)
    assert "alpha" in report.formulations
    assert "beta" in report.formulations
    assert report.formulations["alpha"] == "# alpha formulation"
    assert report.formulations["beta"] == "# beta formulation"


@pytest.mark.asyncio
async def test_formalizer_run_discovers_paradigms_from_disk(tmp_path):
    deep_dir = tmp_path / "deep"
    deep_dir.mkdir()
    (deep_dir / "paradigm-a.md").write_text("Report A")
    (deep_dir / "paradigm-b.md").write_text("Report B")

    client = AsyncMock()
    f = Formalizer(client=client, reports_dir=tmp_path)

    async def fake_run(slug):
        return f"# {slug} content"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run([])

    assert set(report.formulations.keys()) == {"paradigm-a", "paradigm-b"}


@pytest.mark.asyncio
async def test_formalizer_run_handles_partial_failure(tmp_path):
    client = AsyncMock()
    f = Formalizer(client=client, reports_dir=tmp_path)

    call_count = 0

    async def fake_run(slug):
        nonlocal call_count
        call_count += 1
        if slug == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {slug} ok"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run(["good", "fail-me"])

    assert "good" in report.formulations
    assert report.formulations["good"] == "# good ok"
    assert "fail-me" not in report.formulations
