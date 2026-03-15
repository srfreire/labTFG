import json

import pytest
from unittest.mock import AsyncMock, patch

from decisionlab.agents.builder import Builder
from decisionlab.domain.models import BuilderReport


def test_builder_construction(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)
    assert b.client is client
    assert b.reports_dir is tmp_path
    assert b.project_root is project_root


@pytest.mark.asyncio
async def test_builder_run_collects_results(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "alpha-spec1.json").write_text(json.dumps({"paradigm": "alpha", "data": "x"}))
    (reasoner_dir / "beta-spec1.json").write_text(json.dumps({"paradigm": "beta", "data": "y"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(slug, spec_paths):
        return f"# {slug} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["alpha", "beta"])

    assert isinstance(report, BuilderReport)
    assert "alpha" in report.results
    assert "beta" in report.results
    assert report.results["alpha"] == "# alpha built"
    assert report.results["beta"] == "# beta built"


@pytest.mark.asyncio
async def test_builder_run_discovers_paradigms_from_disk(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "paradigm-a-spec1.json").write_text(json.dumps({"paradigm": "paradigm-a", "data": "1"}))
    (reasoner_dir / "paradigm-a-spec2.json").write_text(json.dumps({"paradigm": "paradigm-a", "data": "2"}))
    (reasoner_dir / "paradigm-b-spec1.json").write_text(json.dumps({"paradigm": "paradigm-b", "data": "3"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(slug, spec_paths):
        return f"# {slug} content"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run([])

    assert set(report.results.keys()) == {"paradigm-a", "paradigm-b"}


@pytest.mark.asyncio
async def test_builder_run_handles_partial_failure(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "good-spec.json").write_text(json.dumps({"paradigm": "good", "data": "ok"}))
    (reasoner_dir / "fail-me-spec.json").write_text(json.dumps({"paradigm": "fail-me", "data": "bad"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(slug, spec_paths):
        if slug == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {slug} ok"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run([])

    assert "good" in report.results
    assert report.results["good"] == "# good ok"
    assert "fail-me" not in report.results


@pytest.mark.asyncio
async def test_builder_run_filters_by_paradigm_slugs(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "alpha-spec.json").write_text(json.dumps({"paradigm": "alpha", "data": "a"}))
    (reasoner_dir / "beta-spec.json").write_text(json.dumps({"paradigm": "beta", "data": "b"}))
    (reasoner_dir / "gamma-spec.json").write_text(json.dumps({"paradigm": "gamma", "data": "c"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(slug, spec_paths):
        return f"# {slug} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["alpha", "gamma"])

    assert set(report.results.keys()) == {"alpha", "gamma"}
    assert "beta" not in report.results
