from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.agents.builder import Builder
from decisionlab.domain.models import BuilderReport


def _make_storage(*, exists=True, list_keys=None):
    """Build a storage mock with exists/list helpers."""
    storage = MagicMock()
    storage.exists = AsyncMock(return_value=exists)
    storage.list = AsyncMock(return_value=list_keys or [])
    return storage


def _make_db():
    return MagicMock()


def test_builder_construction(tmp_path):
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        run_id="run-1",
        project_root=project_root,
        storage=_make_storage(),
        db=_make_db(),
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
        storage=_make_storage(exists=True),
        db=_make_db(),
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
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
    storage = _make_storage(
        list_keys=[
            "models/run-1/reasoner/paradigm-a/spec-a.json",
            "models/run-1/reasoner/paradigm-a/spec-b.json",
            "models/run-1/reasoner/paradigm-b/spec-c.json",
        ]
    )
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        project_root=project_root,
        storage=storage,
        db=_make_db(),
    )

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
    client = AsyncMock()
    project_root = tmp_path / "project"
    b = Builder(
        client=client,
        models_prefix="models/run-1",
        project_root=project_root,
        storage=_make_storage(exists=True),
        db=_make_db(),
    )

    async def fake_run(spec_id, spec_path):
        if spec_id == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {spec_id} ok"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
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
        storage=_make_storage(exists=True),
        db=_make_db(),
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run({"alpha": ["spec1", "spec3"], "beta": []})

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
        storage=_make_storage(exists=True),
        db=_make_db(),
    )

    captured_paths = []

    async def fake_run(spec_id, spec_path):
        captured_paths.append((spec_id, spec_path))
        return f"# {spec_id} built"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
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
        storage=_make_storage(exists=True),
        db=_make_db(),
    )

    async def fake_run(spec_id, spec_path):
        return f"# {spec_id} result"

    with patch("decisionlab.agents.builder.BuilderSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await b.run({"homeostatic": ["pi-controller"]})

    assert "pi-controller" in report.results
    assert "homeostatic" not in report.results
