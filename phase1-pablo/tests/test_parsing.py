"""Tests for decisionlab.parsing helpers."""

from __future__ import annotations

from decisionlab.parsing import (
    FORMULATION_HEADER_RE,
    filter_formulations_md,
    parse_formulation_headers,
)

SAMPLE_MD = """\
# Title

Preamble paragraph.

## Formulation 1: Q-Learning Variant
Body of formulation 1.

Some details.

## Formulation 2: Actor-Critic
Body of formulation 2.

## Formulation 3: TD(λ)
Body of formulation 3.
"""


# ---------------------------------------------------------------------------
# FORMULATION_HEADER_RE
# ---------------------------------------------------------------------------


def test_regex_matches_basic_header():
    matches = list(FORMULATION_HEADER_RE.finditer("## Formulation 1: Hello"))
    assert len(matches) == 1
    assert matches[0].group(1) == "1"
    assert matches[0].group(2) == "Hello"


def test_regex_requires_double_hash():
    matches = list(FORMULATION_HEADER_RE.finditer("# Formulation 1: Hello"))
    assert matches == []


def test_regex_handles_multiline():
    matches = list(FORMULATION_HEADER_RE.finditer(SAMPLE_MD))
    nums = [m.group(1) for m in matches]
    assert nums == ["1", "2", "3"]


def test_regex_tolerates_extra_whitespace():
    matches = list(FORMULATION_HEADER_RE.finditer("##   Formulation   42  :  Name "))
    assert len(matches) == 1
    assert matches[0].group(1) == "42"
    # name field includes trailing whitespace; downstream parser strips it
    assert matches[0].group(2).strip() == "Name"


# ---------------------------------------------------------------------------
# parse_formulation_headers
# ---------------------------------------------------------------------------


def test_parse_returns_tuples_with_positions():
    parsed = parse_formulation_headers(SAMPLE_MD)
    assert len(parsed) == 3
    nums = [t[0] for t in parsed]
    names = [t[1] for t in parsed]
    assert nums == [1, 2, 3]
    assert names == ["Q-Learning Variant", "Actor-Critic", "TD(λ)"]
    # Positions form a contiguous, monotonically-growing sequence
    starts = [t[2] for t in parsed]
    ends = [t[3] for t in parsed]
    assert starts == sorted(starts)
    for s, e in zip(starts, ends, strict=True):
        assert s < e
    # Last end is end-of-text
    assert ends[-1] == len(SAMPLE_MD)


def test_parse_returns_empty_when_no_headers():
    assert parse_formulation_headers("# Just a title\n\nSome text.") == []


def test_parse_strips_trailing_whitespace_from_name():
    text = "## Formulation 1: My Name   "
    parsed = parse_formulation_headers(text)
    assert parsed[0][1] == "My Name"


# ---------------------------------------------------------------------------
# filter_formulations_md
# ---------------------------------------------------------------------------


def test_filter_keeps_only_selected():
    result = filter_formulations_md(SAMPLE_MD, [2])
    assert "Formulation 1:" not in result
    assert "Formulation 2:" in result
    assert "Formulation 3:" not in result


def test_filter_preserves_preamble():
    result = filter_formulations_md(SAMPLE_MD, [1])
    assert result.startswith("# Title\n\nPreamble paragraph.")


def test_filter_keeps_multiple_in_order():
    result = filter_formulations_md(SAMPLE_MD, [1, 3])
    f1_idx = result.find("Formulation 1:")
    f3_idx = result.find("Formulation 3:")
    assert f1_idx >= 0
    assert f3_idx >= 0
    assert f1_idx < f3_idx
    assert "Formulation 2:" not in result


def test_filter_returns_text_unchanged_when_no_headers():
    text = "Plain text without any formulation headers."
    assert filter_formulations_md(text, [1, 2]) == text


def test_filter_returns_only_preamble_when_keep_empty():
    result = filter_formulations_md(SAMPLE_MD, [])
    assert "Formulation" not in result
    assert "Preamble" in result


def test_filter_ignores_unknown_numbers():
    result = filter_formulations_md(SAMPLE_MD, [99])
    assert "Formulation" not in result


def test_filter_output_ends_with_single_newline():
    result = filter_formulations_md(SAMPLE_MD, [1, 2])
    assert result.endswith("\n")
    assert not result.endswith("\n\n")
