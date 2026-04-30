from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.agents.builder import Builder
from decisionlab.domain.models import BuilderReport


def test_builder_construction(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        run_id="run-1",
        project_root=project_root,
    )
    assert b.client is client
    assert b.models_prefix == "models/run-1"
    assert b.project_root is project_root


@pytest.mark.asyncio
async def test_builder_run_collects_results(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        run_id="run-1",
        project_root=project_root,
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.exists = AsyncMock(return_value=True)
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        approved = {"alpha": ["spec1"], "beta": ["spec1"]}
        report = await b.run(approved)

    assert isinstance(report, BuilderReport)
    assert "spec1" in report.results


@pytest.mark.asyncio
async def test_builder_run_discovers_specs_from_s3(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        project_root=project_root,
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} content"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.list = AsyncMock(
            return_value=[
                "models/run-1/reasoner/paradigm-a/spec-a.json",
                "models/run-1/reasoner/paradigm-a/spec-b.json",
                "models/run-1/reasoner/paradigm-b/spec-c.json",
            ]
        )
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run()

    assert set(report.results.keys()) == {"spec-a", "spec-b", "spec-c"}


@pytest.mark.asyncio
async def test_builder_run_handles_partial_failure(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        project_root=project_root,
    )

    async def fake_run(spec_id, spec_path):
        if spec_id == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {spec_id} ok"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.exists = AsyncMock(return_value=True)
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run({"paradigm": ["good", "fail-me"]})

    assert "good" in report.results
    assert report.results["good"] == "# good ok"
    assert "fail-me" not in report.results


@pytest.mark.asyncio
async def test_builder_run_filters_by_approved_specs(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        run_id="run-1",
        project_root=project_root,
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.exists = AsyncMock(return_value=True)
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run({"alpha": ["spec1", "spec3"], "beta": []})

    # Only alpha/spec1 and alpha/spec3 were built (beta had no formulations)
    assert "spec1" in report.results
    assert "spec3" in report.results


# ---- P5-003: Slug-based path tests ----


@pytest.mark.asyncio
async def test_builder_constructs_nested_s3_paths(tmp_path):
    """Builder passes correct nested spec paths to sub-agents."""
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        run_id="run-1",
        project_root=project_root,
    )

    captured_paths = []

    async def fake_run(spec_id, spec_path):
        captured_paths.append((spec_id, spec_path))
        return f"# {spec_id} built"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.exists = AsyncMock(return_value=True)
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        await b.run({"homeostatic": ["pi-controller"]})

    assert len(captured_paths) == 1
    spec_id, spec_path = captured_paths[0]
    assert spec_id == "pi-controller"
    assert spec_path == "reasoner/homeostatic/pi-controller.json"


@pytest.mark.asyncio
async def test_builder_results_keyed_by_formulation_slug(tmp_path):
    """build_results uses formulation slugs as keys."""
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        project_root=project_root,
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} result"

    with (
        patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub,
        patch("decisionlab.agents.builder.shared") as mock_shared,
    ):
        mock_shared.storage.exists = AsyncMock(return_value=True)
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run({"homeostatic": ["pi-controller"]})

    assert "pi-controller" in report.results
    assert "homeostatic" not in report.results
