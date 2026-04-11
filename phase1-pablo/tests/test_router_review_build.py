"""Tests for Router._review_build handling of reasoner reruns (P4-002)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.router import PipelineState, Router, Stage


def _make_state(tmp_path: Path) -> PipelineState:
    state = PipelineState(
        stage=Stage.REVIEW_BUILD,
        problem="test problem",
        reports_dir=tmp_path,
        approved_paradigms=["homeostatic"],
        selected_formulations={"homeostatic": ["T01-P01-F01", "T01-P01-F02"]},
        approved_specs=["T01-P01-F01", "T01-P01-F02"],
        build_results={"T01-P01-F01": "Model OK", "T01-P01-F02": "Model OK"},
    )
    state.id_registry = {"homeostatic": "T01-P01"}
    return state


def _make_router(state: PipelineState) -> Router:
    client = AsyncMock()
    search = MagicMock()
    return Router(
        client=client,
        state=state,
        search=search,
        project_root=state.reports_dir.parent,
    )


class TestReviewBuildReasonerReruns:
    @pytest.mark.asyncio
    async def test_reasoner_rerun_triggers_cascade(self, tmp_path):
        """When review_build returns reasoner_reruns, Reasoner and Builder run."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: invalid build triggers reasoner rerun
                return [], [], ["homeostatic"]
            # Second call: all approved after rerun
            return ["T01-P01-F01"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"T01-P01-F01": "Rebuilt OK"}

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
        ):
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst

            await router._review_build()

        # Reasoner was called for the paradigm
        mock_reasoner_inst.run.assert_called_once_with(
            {"homeostatic": ["T01-P01-F01", "T01-P01-F02"]}
        )
        # Builder was called after Reasoner
        mock_builder_inst.run.assert_called_once()
        # State advanced to DONE
        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_no_reasoner_reruns_proceeds_normally(self, tmp_path):
        """Without reasoner_reruns, proceeds to DONE."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["T01-P01-F01", "T01-P01-F02"], [], []

        with patch("decisionlab.feedback.review_build", side_effect=mock_review_build):
            await router._review_build()

        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_rejections_rerun_builder_only(self, tmp_path):
        """Regular rejections re-run only the Builder (not Reasoner)."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [("T01-P01-F01", "homeostatic", "fix tests")], []
            return ["T01-P01-F01"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"T01-P01-F01": "Rebuilt OK"}

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
        ):
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst

            await router._review_build()

        # Builder was called (for rejection rebuild)
        mock_builder_inst.run.assert_called()
        # Reasoner was NOT called
        mock_reasoner_inst.run.assert_not_called()
        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_stale_validation_files_cleaned_after_rerun(self, tmp_path):
        """Validation files are deleted after successful Reasoner→Builder rerun."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        # Write a stale validation report
        builder_dir = tmp_path / "builder"
        builder_dir.mkdir(parents=True)
        vfile = builder_dir / "T01-P01-F01_validation.json"
        vfile.write_text(json.dumps({
            "formulation_id": "T01-P01-F01",
            "paradigm": "homeostatic",
            "status": "invalid",
            "problems": [{"type": "ambiguous_logic", "detail": "test"}],
        }))

        call_count = 0

        async def mock_review_build(reports_dir, build_results):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [], ["homeostatic"]
            return ["T01-P01-F01"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"T01-P01-F01": "Rebuilt OK"}

        with (
            patch("decisionlab.feedback.review_build", side_effect=mock_review_build),
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
            patch("decisionlab.agents.builder.Builder") as MockBuilder,
        ):
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst
            mock_builder_inst = AsyncMock()
            mock_builder_inst.run.return_value = mock_builder_report
            MockBuilder.return_value = mock_builder_inst

            await router._review_build()

        # Validation file should be cleaned up
        assert not vfile.exists()
        assert state.stage == Stage.DONE
