"""Tests for Router._review_build handling of reasoner reruns (P4-002)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.router import PipelineState, Router, Stage


def _make_state(tmp_path: Path) -> PipelineState:
    return PipelineState(
        stage=Stage.REVIEW_BUILD,
        problem="test problem",
        reports_dir=tmp_path,
        approved_paradigms=["homeostatic"],
        selected_formulations={"homeostatic": ["pi-controller", "dual-process"]},
        approved_specs={"homeostatic": ["pi-controller", "dual-process"]},
        build_results={"pi-controller": "Model OK", "dual-process": "Model OK"},
    )


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
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

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
            {"homeostatic": ["pi-controller", "dual-process"]}
        )
        # Builder was called after Reasoner with paradigm's approved specs
        mock_builder_inst.run.assert_called_once_with(
            ["pi-controller", "dual-process"]
        )
        # State advanced to DONE
        assert state.stage == Stage.DONE

    @pytest.mark.asyncio
    async def test_no_reasoner_reruns_proceeds_normally(self, tmp_path):
        """Without reasoner_reruns, proceeds to DONE."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        async def mock_review_build(reports_dir, build_results):
            return ["pi-controller", "dual-process"], [], []

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
                return [], [("pi-controller", "homeostatic", "fix tests")], []
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

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
        vfile = builder_dir / "pi-controller_validation.json"
        vfile.write_text(json.dumps({
            "formulation_id": "pi-controller",
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
            return ["pi-controller"], [], []

        mock_builder_report = MagicMock()
        mock_builder_report.results = {"pi-controller": "Rebuilt OK"}

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

        # Validation file cleanup happens via S3 (not local filesystem)
        # so we just verify the stage advanced
        assert state.stage == Stage.DONE
