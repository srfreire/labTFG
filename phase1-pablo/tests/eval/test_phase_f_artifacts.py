"""Phase F static validation: the suite + fixture artifacts ship correctly.

These tests don't run the suite (that requires live infra and burns API
budget) — they verify the YAML and JSON ship in a shape the harness
accepts and reference predicates that exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decisionlab.canonicalize import CANONICALIZE_LABELS, DEFAULT_THRESHOLD
from decisionlab.eval.assertions import predicate_names
from decisionlab.eval.suite import SuiteSpec
from decisionlab.router import Stage

ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = ROOT / "evals/suites/paradigm-canonicalization.yaml"
PAIRS_PATH = ROOT / "evals/fixtures/canonicalize-pairs.json"


def test_suite_yaml_parses():
    """The new suite parses through the eval harness's loader."""
    spec = SuiteSpec.from_yaml(SUITE_PATH)
    assert spec.name == "paradigm-canonicalization"
    assert spec.stages == (Stage.RESEARCH,)
    assert spec.reset_kg_before is False
    assert len(spec.topics) == 4


def test_suite_predicates_are_registered():
    """Every predicate the suite references must exist in the registry —
    a typo'd predicate name would otherwise pass static parsing but fail
    every topic at runtime."""
    spec = SuiteSpec.from_yaml(SUITE_PATH)
    registered = set(predicate_names())
    seen: set[str] = set()
    for topic in spec.topics:
        for stage_assertions in topic.expect.values():
            for entry in stage_assertions or []:
                if isinstance(entry, dict) and len(entry) == 1:
                    seen.add(next(iter(entry)))
    missing = seen - registered
    assert not missing, (
        f"suite references unknown predicates: {sorted(missing)} "
        f"(registered: {sorted(registered)})"
    )


def test_suite_uses_phase_a_instrumentation():
    """At least one tool_called assertion proves the new instrumentation
    is exercised by the regression suite."""
    spec = SuiteSpec.from_yaml(SUITE_PATH)
    has_tool_called = False
    for topic in spec.topics:
        for stage_assertions in topic.expect.values():
            for entry in stage_assertions or []:
                if isinstance(entry, dict) and "tool_called" in entry:
                    has_tool_called = True
    assert has_tool_called, "regression suite should exercise tool_called"


def test_canonicalize_pairs_fixture_well_formed():
    """The labeled fixture parses and every pair carries the fields used
    to tune τ."""
    data = json.loads(PAIRS_PATH.read_text())
    assert "pairs" in data
    assert isinstance(data["pairs"], list) and data["pairs"]

    valid_labels = set(CANONICALIZE_LABELS)
    for pair in data["pairs"]:
        assert pair["label"] in valid_labels, (
            f"pair label {pair['label']!r} not in CANONICALIZE_LABELS"
        )
        assert isinstance(pair["candidate"], dict)
        assert isinstance(pair["existing"], dict)
        assert isinstance(pair["should_merge"], bool)
        assert isinstance(pair["rationale"], str) and pair["rationale"]


def test_canonicalize_pairs_have_balanced_classes():
    """Sanity: the labeled set should contain both merge=True and
    merge=False examples, otherwise it can't pin down a useful threshold."""
    data = json.loads(PAIRS_PATH.read_text())
    merges = [p for p in data["pairs"] if p["should_merge"]]
    keeps = [p for p in data["pairs"] if not p["should_merge"]]
    assert len(merges) >= 5, "need at least 5 positive examples"
    assert len(keeps) >= 5, "need at least 5 negative examples"


def test_canonicalize_pairs_threshold_documented():
    """The fixture preserves the canonicalize threshold for reference;
    if the canonicalizer's default τ shifts, this catches drift."""
    data = json.loads(PAIRS_PATH.read_text())
    assert data["_threshold_default"] == pytest.approx(DEFAULT_THRESHOLD)
