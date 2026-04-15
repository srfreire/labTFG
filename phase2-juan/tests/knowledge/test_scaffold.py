"""P1-001 scaffold tests — verify public surface + factory error path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.settings import Settings
from simlab.knowledge import (
    ModelInfo,
    SimulationContext,
    TrackerMemoryWriter,
    WriteResult,
    build_writer_from_settings,
)


def test_data_classes_instantiate_with_expected_fields():
    model = ModelInfo(
        model_id="uuid-1",
        class_name="HomeostaticDriveReductionRL",
        paradigm="homeostatic-regulation",
        formulation="drive-reduction-rl",
        phase1_run_id="uuid-run",
    )
    context = SimulationContext(
        phase2_experiment_id="exp-1",
        environment="grid_10x10",
        steps=200,
        seed=42,
        agent_to_model={"agent_0": model},
    )
    result = WriteResult(
        summaries_written=1,
        trajectories_written=2,
        episodes_written=1,
        episodes_filtered=2,
        duration_ms=123,
    )

    assert model.paradigm == "homeostatic-regulation"
    assert context.agent_to_model["agent_0"] is model
    assert result.skipped_reason is None  # default


def test_tracker_memory_writer_constructs_with_mocked_services():
    writer = TrackerMemoryWriter(
        vector_store=MagicMock(),
        embedding_service=MagicMock(),
        db=MagicMock(),
    )
    assert isinstance(writer, TrackerMemoryWriter)


async def test_writer_with_empty_tracker_returns_no_relevant_content():
    writer = TrackerMemoryWriter(
        vector_store=MagicMock(),
        embedding_service=MagicMock(),
        db=MagicMock(),
    )
    context = SimulationContext(
        phase2_experiment_id="exp-1",
        environment="grid_10x10",
        steps=10,
        seed=None,
        agent_to_model={},
    )
    result = await writer.write("{}", context)
    assert result.skipped_reason == "no_relevant_content"
    assert result.summaries_written == 0
    assert result.trajectories_written == 0
    assert result.episodes_written == 0


async def test_build_writer_returns_none_without_voyage_key(caplog):
    settings = Settings(VOYAGE_API_KEY="", ZEROENTROPY_API_KEY="z-key")
    with caplog.at_level("WARNING"):
        result = await build_writer_from_settings(settings)
    assert result is None
    assert any("Voyage" in r.message for r in caplog.records)


async def test_build_writer_returns_none_without_zeroentropy_key(caplog):
    settings = Settings(VOYAGE_API_KEY="v-key", ZEROENTROPY_API_KEY="")
    with caplog.at_level("WARNING"):
        result = await build_writer_from_settings(settings)
    assert result is None
    assert any("ZeroEntropy" in r.message or "Voyage" in r.message for r in caplog.records)


async def test_build_writer_returns_none_if_postgres_fails(caplog):
    settings = Settings(VOYAGE_API_KEY="v-key", ZEROENTROPY_API_KEY="z-key")
    with patch("shared.database.DatabaseService.connect", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with caplog.at_level("WARNING"):
            result = await build_writer_from_settings(settings)
    assert result is None
    assert any("Postgres" in r.message for r in caplog.records)
