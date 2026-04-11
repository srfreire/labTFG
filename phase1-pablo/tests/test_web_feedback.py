"""Tests for web_feedback.py review_reason with invalid specs (P4-001)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.web_feedback import review_reason


def _make_valid_spec(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "name": f"Valid ({formulation_id})",
        "description": "A valid spec.",
        "variables": [],
        "parameters": [],
        "rules": [],
        "decision_logic": {"description": "...", "pseudocode": ["return Action('stay')"]},
        "env_mapping": {"perception_to_variables": {}, "actions_used": ["stay"], "reward_source": "none"},
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
        invalid = _make_invalid_spec("T01-P01-F01", "homeostatic")
        _write_spec(tmp_path, invalid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "T01-P01-F01": {"rerun_formalizer": True},
                },
            }
            approved, rejections, formalizer_reruns = await review_reason(
                tmp_path, emit,
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
        valid = _make_valid_spec("T01-P01-F01", "homeostatic")
        invalid = _make_invalid_spec("T01-P01-F02", "homeostatic")
        _write_spec(tmp_path, valid)
        _write_spec(tmp_path, invalid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {
                    "T01-P01-F01": {"approved": True},
                    "T01-P01-F02": {"rerun_formalizer": True},
                },
            }
            approved, rejections, formalizer_reruns = await review_reason(
                tmp_path, emit,
            )

        assert "T01-P01-F01" in approved
        assert "homeostatic" in formalizer_reruns
        assert len(rejections) == 0

    @pytest.mark.asyncio
    async def test_all_valid_returns_empty_formalizer_reruns(self, tmp_path):
        """When all specs valid, formalizer_reruns is empty."""
        valid = _make_valid_spec("T01-P01-F01", "homeostatic")
        _write_spec(tmp_path, valid)

        emit = AsyncMock()

        with patch("decisionlab.web_feedback.wait_for_review") as mock_wait:
            mock_wait.return_value = {
                "decisions": {"T01-P01-F01": {"approved": True}},
            }
            approved, rejections, formalizer_reruns = await review_reason(
                tmp_path, emit,
            )

        assert "T01-P01-F01" in approved
        assert len(formalizer_reruns) == 0
