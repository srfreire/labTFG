"""Tests for pure helper functions in feedback.py."""

from decisionlab.feedback import (
    _discover_paradigm_slugs,
    _filter_formulations_md,
    _parse_formulation_headers,
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
# _parse_formulation_headers
# ---------------------------------------------------------------------------


class TestParseFormulationHeaders:
    def test_parse_single_formulation(self):
        headers = _parse_formulation_headers(SINGLE_FORMULATION_MD)
        assert len(headers) == 1
        num, name, start, end = headers[0]
        assert num == 1
        assert name == "Only One"
        assert start == 0
        assert end == len(SINGLE_FORMULATION_MD)

    def test_parse_multiple_formulations(self):
        headers = _parse_formulation_headers(SAMPLE_MD)
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
        headers = _parse_formulation_headers(text)
        assert headers == []

    def test_parse_formulation_with_preamble(self):
        text = "# Preamble title\n\nIntro text.\n\n## Formulation 1: First\nContent.\n"
        headers = _parse_formulation_headers(text)
        assert len(headers) == 1
        num, name, start, _ = headers[0]
        assert num == 1
        assert name == "First"
        # Preamble is before the first header
        assert start > 0
        assert text[:start].startswith("# Preamble")


# ---------------------------------------------------------------------------
# _filter_formulations_md
# ---------------------------------------------------------------------------


class TestFilterFormulationsMd:
    def test_filter_keeps_selected(self):
        result = _filter_formulations_md(SAMPLE_MD, [1, 3])
        assert "## Formulation 1: Basic Homeostasis" in result
        assert "## Formulation 3: Full Integration" in result
        assert "## Formulation 2: Extended Model" not in result

    def test_filter_preserves_preamble(self):
        result = _filter_formulations_md(SAMPLE_MD, [1])
        assert result.startswith("# Paradigm: Homeostatic Regulation")

    def test_filter_no_headers(self):
        text = "# No formulations here\n\nJust plain text.\n"
        result = _filter_formulations_md(text, [1, 2])
        assert result == text

    def test_filter_keeps_all(self):
        result = _filter_formulations_md(SAMPLE_MD, [1, 2, 3])
        # All three formulations present
        assert "## Formulation 1" in result
        assert "## Formulation 2" in result
        assert "## Formulation 3" in result

    def test_filter_empty_selection(self):
        result = _filter_formulations_md(SAMPLE_MD, [])
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
