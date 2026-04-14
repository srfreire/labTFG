"""Tests for pure helper functions in feedback.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from decisionlab.feedback import (
    _discover_paradigm_slugs,
    review_build,
    review_reason,
)
from decisionlab.parsing import (
    filter_formulations_md,
    parse_formulation_headers,
)

# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# Paradigm: Homeostatic Regulation

## Formulation 1: Basic Homeostasis
Content for formulation 1...
Some more details here.

## Formulation 2: Extended Model
Content for formulation 2...
Extended details here.

## Formulation 3: Full Integration
Content for formulation 3...
Final details here.
"""

SINGLE_FORMULATION_MD = """\
## Formulation 1: Only One
Single formulation content.
"""


# ---------------------------------------------------------------------------
# parse_formulation_headers
# ---------------------------------------------------------------------------


class TestParseFormulationHeaders:
    def test_parse_single_formulation(self):
        headers = parse_formulation_headers(SINGLE_FORMULATION_MD)
        assert len(headers) == 1
        num, name, start, end = headers[0]
        assert num == 1
        assert name == "Only One"
        assert start == 0
        assert end == len(SINGLE_FORMULATION_MD)

    def test_parse_multiple_formulations(self):
        headers = parse_formulation_headers(SAMPLE_MD)
        assert len(headers) == 3

        assert headers[0][0] == 1
        assert headers[0][1] == "Basic Homeostasis"

        assert headers[1][0] == 2
        assert headers[1][1] == "Extended Model"

        assert headers[2][0] == 3
        assert headers[2][1] == "Full Integration"

        # Each section's end == next section's start (except last == EOF)
        assert headers[0][3] == headers[1][2]
        assert headers[1][3] == headers[2][2]
        assert headers[2][3] == len(SAMPLE_MD)

    def test_parse_no_formulations(self):
        text = "# Just a title\n\nSome paragraph text.\n"
        headers = parse_formulation_headers(text)
        assert headers == []

    def test_parse_formulation_with_preamble(self):
        text = "# Preamble title\n\nIntro text.\n\n## Formulation 1: First\nContent.\n"
        headers = parse_formulation_headers(text)
        assert len(headers) == 1
        num, name, start, _ = headers[0]
        assert num == 1
        assert name == "First"
        # Preamble is before the first header
        assert start > 0
        assert text[:start].startswith("# Preamble")


# ---------------------------------------------------------------------------
# filter_formulations_md
# ---------------------------------------------------------------------------


class TestFilterFormulationsMd:
    def test_filter_keeps_selected(self):
        result = filter_formulations_md(SAMPLE_MD, [1, 3])
        assert "## Formulation 1: Basic Homeostasis" in result
        assert "## Formulation 3: Full Integration" in result
        assert "## Formulation 2: Extended Model" not in result

    def test_filter_preserves_preamble(self):
        result = filter_formulations_md(SAMPLE_MD, [1])
        assert result.startswith("# Paradigm: Homeostatic Regulation")

    def test_filter_no_headers(self):
        text = "# No formulations here\n\nJust plain text.\n"
        result = filter_formulations_md(text, [1, 2])
        assert result == text

    def test_filter_keeps_all(self):
        result = filter_formulations_md(SAMPLE_MD, [1, 2, 3])
        # All three formulations present
        assert "## Formulation 1" in result
        assert "## Formulation 2" in result
        assert "## Formulation 3" in result

    def test_filter_empty_selection(self):
        result = filter_formulations_md(SAMPLE_MD, [])
        # Only the preamble should remain
        assert "# Paradigm: Homeostatic Regulation" in result
        assert "## Formulation 1" not in result
        assert "## Formulation 2" not in result
        assert "## Formulation 3" not in result


# ---------------------------------------------------------------------------
# _discover_paradigm_slugs
# ---------------------------------------------------------------------------


class TestDiscoverParadigmSlugs:
    def test_discover_finds_md_files(self, tmp_path):
        deep = tmp_path / "deep"
        deep.mkdir()
        (deep / "homeostatic.md").write_text("# Homeostatic")
        (deep / "hedonic.md").write_text("# Hedonic")
        (deep / "integrated.md").write_text("# Integrated")

        slugs = _discover_paradigm_slugs(tmp_path)
        assert slugs == ["hedonic", "homeostatic", "integrated"]

    def test_discover_empty_dir(self, tmp_path):
        deep = tmp_path / "deep"
        deep.mkdir()

        slugs = _discover_paradigm_slugs(tmp_path)
        assert slugs == []

    def test_discover_no_deep_dir(self, tmp_path):
        slugs = _discover_paradigm_slugs(tmp_path)
        assert slugs == []


# ---------------------------------------------------------------------------
# P4-001: review_reason with invalid specs
# ---------------------------------------------------------------------------


def _make_valid_spec(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "name": f"Valid Spec ({formulation_id})",
        "description": "A valid spec.",
        "variables": [{"symbol": "X", "name": "x_var", "description": "...", "type": "float", "initial_value": 0.0, "range": [0, 1]}],
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
            {"type": "undefined_variable", "detail": "Variable 'Z' used in rule R2 but not defined"},
            {"type": "unreasonable_default", "detail": "Parameter 'rate' has default 0"},
        ],
    }


def _write_spec(reports_dir, spec: dict) -> None:
    reasoner_dir = reports_dir / "reasoner"
    reasoner_dir.mkdir(parents=True, exist_ok=True)
    fid = spec["formulation_id"]
    (reasoner_dir / f"{fid}.json").write_text(json.dumps(spec, indent=2))


class TestReviewReasonInvalidSpecs:
    @pytest.mark.asyncio
    async def test_invalid_spec_detected_and_user_chooses_rerun(self, tmp_path):
        """Invalid spec triggers rerun option; user chooses rerun formalizer."""
        valid = _make_valid_spec("pi-controller", "homeostatic")
        invalid = _make_invalid_spec("dual-process", "homeostatic")
        _write_spec(tmp_path, valid)
        _write_spec(tmp_path, invalid)

        # Mock questionary: approve the valid spec, then choose "rerun formalizer" for invalid
        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [
                True,   # approve valid spec pi-controller
                True,   # rerun formalizer for invalid dual-process
            ]
            approved, rejections, formalizer_reruns = await review_reason(tmp_path)

        assert "pi-controller" in approved
        assert "dual-process" not in approved
        assert len(rejections) == 0
        assert "homeostatic" in formalizer_reruns

    @pytest.mark.asyncio
    async def test_invalid_spec_detected_and_user_skips(self, tmp_path):
        """Invalid spec, user chooses to skip (not rerun)."""
        invalid = _make_invalid_spec("pi-controller", "homeostatic")
        _write_spec(tmp_path, invalid)

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [
                False,  # skip (don't rerun formalizer)
            ]
            approved, rejections, formalizer_reruns = await review_reason(tmp_path)

        assert len(approved) == 0
        assert len(rejections) == 0
        assert len(formalizer_reruns) == 0

    @pytest.mark.asyncio
    async def test_all_valid_specs_returns_empty_formalizer_reruns(self, tmp_path):
        """When all specs are valid, formalizer_reruns is empty."""
        valid = _make_valid_spec("pi-controller", "homeostatic")
        _write_spec(tmp_path, valid)

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [True]  # approve
            approved, rejections, formalizer_reruns = await review_reason(tmp_path)

        assert "pi-controller" in approved
        assert len(formalizer_reruns) == 0

    @pytest.mark.asyncio
    async def test_duplicate_paradigm_deduplication(self, tmp_path):
        """Two invalid specs for the same paradigm produce one formalizer rerun."""
        inv1 = _make_invalid_spec("pi-controller", "homeostatic")
        inv2 = _make_invalid_spec("dual-process", "homeostatic")
        _write_spec(tmp_path, inv1)
        _write_spec(tmp_path, inv2)

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [True, True]  # rerun for both
            approved, rejections, formalizer_reruns = await review_reason(tmp_path)

        assert len(formalizer_reruns) == 1
        assert formalizer_reruns == ["homeostatic"]


# ---------------------------------------------------------------------------
# P4-002: review_build with invalid builds
# ---------------------------------------------------------------------------


def _make_invalid_build(formulation_id: str, paradigm: str) -> dict:
    return {
        "formulation_id": formulation_id,
        "paradigm": paradigm,
        "status": "invalid",
        "problems": [
            {"type": "ambiguous_logic", "detail": "Step 3 says 'choose wisely'"},
            {"type": "missing_perception_key", "detail": "'temperature' not in perception"},
        ],
    }


def _write_validation(reports_dir, data: dict) -> None:
    builder_dir = reports_dir / "builder"
    builder_dir.mkdir(parents=True, exist_ok=True)
    fid = data["formulation_id"]
    (builder_dir / f"{fid}_validation.json").write_text(json.dumps(data, indent=2))


class TestReviewBuildInvalidBuilds:
    @pytest.mark.asyncio
    async def test_invalid_build_detected_and_user_chooses_rerun(self, tmp_path):
        """Invalid build triggers rerun option; user chooses rerun reasoner."""
        _write_validation(tmp_path, _make_invalid_build("pi-controller", "homeostatic"))

        build_results = {"dual-process": "Implemented model and tests passed."}

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [
                True,   # rerun reasoner for invalid pi-controller
                True,   # approve valid build dual-process
            ]
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path, build_results,
            )

        assert "dual-process" in approved
        assert "pi-controller" not in approved
        assert len(rejections) == 0
        assert "homeostatic" in reasoner_reruns

    @pytest.mark.asyncio
    async def test_invalid_build_detected_and_user_skips(self, tmp_path):
        """Invalid build, user chooses to skip (not rerun)."""
        _write_validation(tmp_path, _make_invalid_build("pi-controller", "homeostatic"))

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [
                False,  # skip (don't rerun reasoner)
            ]
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path, {},
            )

        assert len(approved) == 0
        assert len(rejections) == 0
        assert len(reasoner_reruns) == 0

    @pytest.mark.asyncio
    async def test_all_valid_builds_returns_empty_reasoner_reruns(self, tmp_path):
        """When all builds are valid, reasoner_reruns is empty."""
        build_results = {"pi-controller": "Model implemented. All tests passed."}

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [True]  # approve
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path, build_results,
            )

        assert "pi-controller" in approved
        assert len(reasoner_reruns) == 0

    @pytest.mark.asyncio
    async def test_duplicate_paradigm_deduplication(self, tmp_path):
        """Two invalid builds for the same paradigm produce one reasoner rerun."""
        _write_validation(tmp_path, _make_invalid_build("pi-controller", "homeostatic"))
        _write_validation(tmp_path, _make_invalid_build("dual-process", "homeostatic"))

        with patch("decisionlab.feedback._ask") as mock_ask:
            mock_ask.side_effect = [True, True]  # rerun for both
            approved, rejections, reasoner_reruns = await review_build(
                tmp_path, {},
            )

        assert len(reasoner_reruns) == 1
        assert reasoner_reruns == ["homeostatic"]
