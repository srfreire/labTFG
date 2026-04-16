"""E2E test: PipelineState save/load against real S3.

Exercises the persistence side of the Router state machine without
running the full agent loop.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from decisionlab.router import PipelineState, Stage

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_pipeline_state_save_and_load_round_trip(shared_initialized, tmp_path):
    """A PipelineState saved to S3 can be loaded back exactly."""
    run_id = str(uuid.uuid4())
    state = PipelineState(
        stage=Stage.FORMALIZE,
        problem="how do animals decide?",
        reports_dir=tmp_path,
        run_id=run_id,
        approved_paradigms=["hedonic", "homeostatic"],
        selected_formulations={"hedonic": ["q-learning"], "homeostatic": ["pid-loop"]},
    )

    await state.save()

    loaded = await PipelineState.load(run_id)
    assert loaded.stage == Stage.FORMALIZE
    assert loaded.problem == "how do animals decide?"
    assert loaded.run_id == run_id
    assert loaded.approved_paradigms == ["hedonic", "homeostatic"]
    assert loaded.selected_formulations == {
        "hedonic": ["q-learning"],
        "homeostatic": ["pid-loop"],
    }


@pytest.mark.asyncio
async def test_pipeline_state_default_values(shared_initialized, tmp_path):
    """Defaulted fields persist correctly across save/load."""
    run_id = str(uuid.uuid4())
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="x",
        reports_dir=tmp_path,
        run_id=run_id,
    )
    await state.save()
    loaded = await PipelineState.load(run_id)
    assert loaded.stage == Stage.RESEARCH
    assert loaded.approved_paradigms == []
    assert loaded.selected_formulations == {}
    assert loaded.approved_specs == {}


@pytest.mark.asyncio
async def test_pipeline_state_load_returns_path_for_reports_dir(
    shared_initialized, tmp_path,
):
    """reports_dir is not persisted by save(); loaded value defaults to Path('.')."""
    run_id = str(uuid.uuid4())
    state = PipelineState(
        stage=Stage.BUILD,
        problem="x",
        reports_dir=tmp_path,
        run_id=run_id,
    )
    await state.save()
    loaded = await PipelineState.load(run_id)
    assert isinstance(loaded.reports_dir, Path)


@pytest.mark.asyncio
async def test_pipeline_state_load_missing_raises_file_not_found(
    shared_initialized,
):
    """Loading a non-existent run raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        await PipelineState.load("nonexistent-run-" + uuid.uuid4().hex)
