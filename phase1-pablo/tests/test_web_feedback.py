"""Tests for web_feedback.py review stages with invalid specs/builds (P4-001, P4-002)."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from decisionlab import web_feedback
from decisionlab.web_feedback import review_build, review_reason


@pytest.fixture(autouse=True)
def clear_review_globals():
    web_feedback._review_events.clear()
    web_feedback._review_responses.clear()
    yield
    web_feedback._review_events.clear()
    web_feedback._review_responses.clear()


class TestReviewResponseCoordination:
    def test_unsolicited_response_is_ignored(self):
        web_feedback.handle_review_response("review_research", {"approved": ["x"]})

        assert web_feedback._review_events == {}
        assert web_feedback._review_responses == {}

    @pytest.mark.asyncio
    async def test_wait_for_review_cleans_up_on_cancellation(self):
        emit = AsyncMock()
        task = asyncio.create_task(
            web_feedback.wait_for_review("review_research", emit, {"paradigms": []})
        )
        await asyncio.sleep(0)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert web_feedback._review_events == {}
        assert web_feedback._review_responses == {}


def _make_valid_spec(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "name": f"Valid ({formulation_id})",
        "description": "A valid spec.",
        "variables": [],
        "parameters": [],
        "rules": [],
        "decision_logic": {
            "description": "...",
            "pseudocode": ["return Action('stay')"],
        },
        "env_mapping": {
            "perception_to_variables": {},
            "actions_used": ["stay"],
            "reward_source": "none",
        },
        "expected_behaviors": [],
        "references": [],
    }


def _make_invalid_spec(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "status": "invalid",
        "problems": [
            {"type": "undefined_variable", "detail": "Variable 'Z' not defined"},
        ],
    }


def _write_spec(reports_dir, spec: dict) -> None:
    reasoner_dir = reports_dir / "reasoner"
    reasoner_dir.mkdir(parents=True, exist_ok=True)
    fid = spec["formulation_id"]
    (reasoner_dir / f"{fid}.json").write_text(json.dumps(spec, indent=2))


class TestWebReviewReasonInvalidSpecs:
    @pytest.mark.asyncio
    async def test_invalid_spec_sent_with_status_and_problems(self, tmp_path):
        """Invalid specs include status and problems in data sent to frontend."""
        invalid = _make_invalid_spec("pi-controller", "homeostatic")
        _write_spec(tmp_path, invalid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "pi-controller": {"rerun_formalizer": True},
                },
            }
            approved, rejections, formalizer_reruns = await review_reason(
                tmp_path,
                emit,
            )

        # Verify the data sent to frontend includes invalid status
        call_args = mock_wait.call_args
        specs_payload = call_args[0][2]["specs"]
        assert len(specs_payload) == 1
        assert specs_payload[0]["status"] == "invalid"
        assert len(specs_payload[0]["problems"]) == 1

        # Verify return values
        assert len(approved) == 0
        assert len(rejections) == 0
        assert "homeostatic" in formalizer_reruns

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_specs(self, tmp_path):
        """Mix of valid and invalid specs processed correctly."""
        valid = _make_valid_spec("pi-controller", "homeostatic")
        invalid = _make_invalid_spec("dual-process", "homeostatic")
        _write_spec(tmp_path, valid)
        _write_spec(tmp_path, invalid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "pi-controller": {"approved": True},
                    "dual-process": {"rerun_formalizer": True},
                },
            }
            approved, rejections, formalizer_reruns = await review_reason(
                tmp_path,
                emit,
            )

        assert "pi-controller" in approved
        assert "homeostatic" in formalizer_reruns
        assert len(rejections) == 0

    @pytest.mark.asyncio
    async def test_all_valid_returns_empty_formalizer_reruns(self, tmp_path):
        """When all specs valid, formalizer_reruns is empty."""
        valid = _make_valid_spec("pi-controller", "homeostatic")
        _write_spec(tmp_path, valid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {"pi-controller": {"approved": True}},
            }
            approved, _rejections, formalizer_reruns = await review_reason(
                tmp_path,
                emit,
            )

        assert "pi-controller" in approved
        assert len(formalizer_reruns) == 0


# ---------------------------------------------------------------------------
# P4-002: web review_build with invalid builds
# ---------------------------------------------------------------------------


def _make_invalid_build(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "status": "invalid",
        "problems": [
            {"type": "ambiguous_logic", "detail": "Step 3 says 'choose wisely'"},
        ],
    }


def _write_validation(reports_dir, data: dict) -> None:
    builder_dir = reports_dir / "builder"
    builder_dir.mkdir(parents=True, exist_ok=True)
    fid = data["formulation_id"]
    (builder_dir / f"{fid}_validation.json").write_text(json.dumps(data, indent=2))


class TestWebReviewBuildInvalidBuilds:
    @pytest.mark.asyncio
    async def test_invalid_build_sent_with_status_and_problems(self, tmp_path):
        """Invalid builds include status and problems in data sent to frontend."""
        _write_validation(tmp_path, _make_invalid_build("pi-controller", "homeostatic"))

        emit = AsyncMock()
        build_results = {"dual-process": "Model implemented. All tests passed."}

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "pi-controller": {"rerun_reasoner": True},
                    "dual-process": {"approved": True},
                },
            }
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path,
                build_results,
                emit,
            )

        # Verify the data sent to frontend includes invalid builds
        call_args = mock_wait.call_args
        payload = call_args[0][2]
        invalid_models = [m for m in payload["models"] if m.get("status") == "invalid"]
        assert len(invalid_models) == 1
        assert len(invalid_models[0]["problems"]) == 1

        # Verify return values
        assert "dual-process" in approved
        assert len(rejections) == 0
        assert "homeostatic" in reasoner_reruns

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_builds(self, tmp_path):
        """Mix of valid and invalid builds processed correctly."""
        _write_validation(tmp_path, _make_invalid_build("dual-process", "homeostatic"))
        build_results = {"pi-controller": "Model implemented."}

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "pi-controller": {"approved": True},
                    "dual-process": {"rerun_reasoner": True},
                },
            }
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path,
                build_results,
                emit,
            )

        assert "pi-controller" in approved
        assert "homeostatic" in reasoner_reruns
        assert len(rejections) == 0

    @pytest.mark.asyncio
    async def test_all_valid_returns_empty_reasoner_reruns(self, tmp_path):
        """When all builds valid, reasoner_reruns is empty."""
        build_results = {"pi-controller": "All tests passed."}
        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {"pi-controller": {"approved": True}},
            }
            approved, _rejections, reasoner_reruns = await review_build(
                tmp_path,
                build_results,
                emit,
            )

        assert "pi-controller" in approved
        assert len(reasoner_reruns) == 0
