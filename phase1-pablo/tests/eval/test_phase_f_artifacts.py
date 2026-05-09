"""Phase F static validation: the suite + fixture artifacts ship correctly.

These tests don't run the suite (that requires live infra and burns API
budget) — they verify the YAML and JSON ship in a shape the harness
accepts and reference predicates that exist.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from decisionlab.eval.assertions import predicate_names
from decisionlab.eval.suite import SuiteSpec
from decisionlab.router import Stage

ROOT = Path(__file__).resolve().parents[2]
SUITE_PATH = ROOT / "evals/suites/paradigm-canonicalization.yaml"
CANONICAL_PARADIGMS_PATH = files("decisionlab.data") / "canonical-paradigms.json"


def test_suite_yaml_parses():
    """The new suite parses through the eval harness's loader.

    Post-2026-05-09 the suite is self-contained: `seed_canonical_paradigms`
    runs in setup so `paradigm_reused` predicates have something to reuse
    against, and `reset_kg_before: true` keeps the run deterministic.
    """
    spec = SuiteSpec.from_yaml(SUITE_PATH)
    assert spec.name == "paradigm-canonicalization"
    assert spec.stages == (Stage.RESEARCH,)
    assert spec.reset_kg_before is True
    assert len(spec.topics) == 4
    assert any(
        action.kind == "seed_canonical_paradigms" for action in spec.setup
    ), "suite must seed canonical paradigms before topics run"


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


def test_canonical_paradigms_fixture_shape():
    """The umbrella classifier seed fixture is a list of {slug,name,definition}.

    The classifier reads this at startup; a malformed fixture would crash
    every fresh ``decisionlab kg seed`` and disable the anchoring
    machinery. Validate static shape so the failure surfaces in CI
    rather than at run time.
    """
    data = json.loads(CANONICAL_PARADIGMS_PATH.read_text())
    assert isinstance(data, list) and data, "expected a non-empty list"
    seen_slugs: set[str] = set()
    for entry in data:
        assert isinstance(entry, dict)
        for required in ("slug", "name", "definition"):
            assert required in entry, f"entry missing {required!r}: {entry}"
            assert isinstance(entry[required], str) and entry[required].strip()
        slug = entry["slug"]
        assert slug == slug.lower(), f"slug must be lowercase: {slug!r}"
        assert " " not in slug, f"slug must be kebab-case: {slug!r}"
        assert slug not in seen_slugs, f"duplicate slug: {slug!r}"
        seen_slugs.add(slug)
