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
    (reasoner_dir / "alpha-spec1.json").write_text(json.dumps({"paradigm": "alpha"}))
    (reasoner_dir / "beta-spec1.json").write_text(json.dumps({"paradigm": "beta"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["alpha-spec1", "beta-spec1"])

    assert isinstance(report, BuilderReport)
    assert "alpha-spec1" in report.results
    assert "beta-spec1" in report.results
    assert report.results["alpha-spec1"] == "# alpha-spec1 built"


@pytest.mark.asyncio
async def test_builder_run_discovers_specs_from_disk(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "spec-a.json").write_text(json.dumps({"paradigm": "a"}))
    (reasoner_dir / "spec-b.json").write_text(json.dumps({"paradigm": "a"}))
    (reasoner_dir / "spec-c.json").write_text(json.dumps({"paradigm": "b"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} content"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run()

    assert set(report.results.keys()) == {"spec-a", "spec-b", "spec-c"}


@pytest.mark.asyncio
async def test_builder_run_handles_partial_failure(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "good-spec.json").write_text(json.dumps({"paradigm": "good"}))
    (reasoner_dir / "fail-me-spec.json").write_text(json.dumps({"paradigm": "bad"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        if spec_id == "fail-me-spec":
            raise RuntimeError("LLM exploded")
        return f"# {spec_id} ok"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run()

    assert "good-spec" in report.results
    assert report.results["good-spec"] == "# good-spec ok"
    assert "fail-me-spec" not in report.results


@pytest.mark.asyncio
async def test_builder_run_filters_by_spec_ids(tmp_path):
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "alpha.json").write_text(json.dumps({"paradigm": "a"}))
    (reasoner_dir / "beta.json").write_text(json.dumps({"paradigm": "b"}))
    (reasoner_dir / "gamma.json").write_text(json.dumps({"paradigm": "c"}))

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["alpha", "gamma"])

    assert set(report.results.keys()) == {"alpha", "gamma"}
    assert "beta" not in report.results


# ---- P1-003: ID propagation tests ----


@pytest.mark.asyncio
async def test_builder_run_with_registry_ids(tmp_path):
    """Builder.run accepts formulation IDs and dispatches per spec."""
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "T01-P01-F01.json").write_text(
        json.dumps({"formulation_id": "T01-P01-F01", "paradigm": "homeostatic"})
    )
    (reasoner_dir / "T01-P01-F02.json").write_text(
        json.dumps({"formulation_id": "T01-P01-F02", "paradigm": "homeostatic"})
    )
    (reasoner_dir / "T01-P02-F01.json").write_text(
        json.dumps({"formulation_id": "T01-P02-F01", "paradigm": "hedonic"})
    )

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["T01-P01-F01", "T01-P02-F01"])

    assert isinstance(report, BuilderReport)
    assert set(report.results.keys()) == {"T01-P01-F01", "T01-P02-F01"}
    assert report.results["T01-P01-F01"] == "# T01-P01-F01 built"
    assert "T01-P01-F02" not in report.results


@pytest.mark.asyncio
async def test_builder_results_keyed_by_formulation_id(tmp_path):
    """build_results uses formulation IDs as keys, not paradigm slugs."""
    reasoner_dir = tmp_path / "reasoner"
    reasoner_dir.mkdir()
    (reasoner_dir / "T01-P01-F01.json").write_text(
        json.dumps({"formulation_id": "T01-P01-F01", "paradigm": "homeostatic"})
    )

    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(client=client, reports_dir=tmp_path, project_root=project_root)

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} result"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run(["T01-P01-F01"])

    assert "T01-P01-F01" in report.results
    assert "homeostatic" not in report.results
