"""Tests for Router._review_reason handling of formalizer reruns (P4-001)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.router import PipelineState, Router, Stage


def _make_state(tmp_path: Path) -> PipelineState:
    state = PipelineState(
        stage=Stage.REVIEW_REASON,
        problem="test problem",
        reports_dir=tmp_path,
        approved_paradigms=["homeostatic"],
        selected_formulations={"homeostatic": ["T01-P01-F01", "T01-P01-F02"]},
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


class TestReviewReasonFormalizerReruns:
    @pytest.mark.asyncio
    async def test_formalizer_rerun_triggers_cascade(self, tmp_path):
        """When review_reason returns formalizer_reruns, Formalizer and Reasoner run."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_reason(reports_dir):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: invalid spec triggers formalizer rerun
                return [], [], ["homeostatic"]
            # Second call: all approved after rerun
            return ["T01-P01-F01"], [], []

        with (
            patch("decisionlab.feedback.review_reason", side_effect=mock_review_reason),
            patch("decisionlab.agents.formalizer.Formalizer") as MockFormalizer,
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
        ):
            mock_formalizer_inst = AsyncMock()
            MockFormalizer.return_value = mock_formalizer_inst
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst

            await router._review_reason()

        # Formalizer was called for the paradigm
        mock_formalizer_inst.run.assert_called_once_with(["homeostatic"])
        # Reasoner was called after Formalizer
        mock_reasoner_inst.run.assert_called_once_with(
            {"homeostatic": ["T01-P01-F01", "T01-P01-F02"]}
        )
        # State advanced to BUILD
        assert state.stage == Stage.BUILD
        assert "T01-P01-F01" in state.approved_specs

    @pytest.mark.asyncio
    async def test_no_formalizer_reruns_proceeds_normally(self, tmp_path):
        """Without formalizer_reruns, proceeds as before (just rejections or approval)."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        async def mock_review_reason(reports_dir):
            return ["T01-P01-F01", "T01-P01-F02"], [], []

        with patch("decisionlab.feedback.review_reason", side_effect=mock_review_reason):
            await router._review_reason()

        assert state.stage == Stage.BUILD
        assert state.approved_specs == ["T01-P01-F01", "T01-P01-F02"]

    @pytest.mark.asyncio
    async def test_rejections_still_rerun_reasoner(self, tmp_path):
        """Regular rejections still re-run only the Reasoner (not Formalizer)."""
        state = _make_state(tmp_path)
        router = _make_router(state)

        call_count = 0

        async def mock_review_reason(reports_dir):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [], [("T01-P01-F01", "homeostatic", "fix equations")], []
            return ["T01-P01-F01"], [], []

        with (
            patch("decisionlab.feedback.review_reason", side_effect=mock_review_reason),
            patch("decisionlab.agents.reasoner.Reasoner") as MockReasoner,
            patch("decisionlab.agents.formalizer.Formalizer") as MockFormalizer,
        ):
            mock_reasoner_inst = AsyncMock()
            MockReasoner.return_value = mock_reasoner_inst
            mock_formalizer_inst = AsyncMock()
            MockFormalizer.return_value = mock_formalizer_inst

            await router._review_reason()

        # Reasoner was called (for rejection)
        mock_reasoner_inst.run.assert_called()
        # Formalizer was NOT called
        mock_formalizer_inst.run.assert_not_called()
        assert state.stage == Stage.BUILD
