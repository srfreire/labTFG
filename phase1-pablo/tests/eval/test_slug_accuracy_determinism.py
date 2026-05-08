"""Determinism contract for the slug-accuracy suite (P0-003).

Phase 0 R3: ``slug-accuracy.yaml`` flipped to ``reset_kg_before: true``
and gained a ``setup`` block that seeds ``canonical-paradigms.json``
before every run. Two back-to-back invocations must therefore produce
identical assertion outcomes — anything else means residue is leaking
between runs.

The test stubs ``run_pipeline`` so we don't burn Anthropic budget, but
keeps the rest of the wiring real: the suite YAML is loaded from disk,
the eval-KG segregation guard runs, ``kgadmin.reset`` actually wipes
Neo4j, and the canonical-paradigms seed lands real ``Paradigm`` nodes.
The stub mirrors what the real Researcher would do: produces a
``PipelineRunResult`` whose ``paradigms`` matches the YAML's
``expect.research`` so per-topic assertions evaluate consistently
across runs.

Run with:

    docker compose up -d postgres minio neo4j qdrant
    cd shared && uv run alembic upgrade head
    LABTFG_EVAL_KG=1 uv run pytest \
        tests/eval/test_slug_accuracy_determinism.py -m integration
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import shared
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import SuiteSpec, run_suite
from decisionlab.router import Stage
from decisionlab.runtime.tool_calls import ToolCall

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SLUG_ACCURACY_PATH = REPO_ROOT / "evals/suites/slug-accuracy.yaml"


@pytest.fixture
async def live_eval_kg(monkeypatch):
    """Boot ``shared`` against the LABTFG_EVAL_KG-marked Neo4j and clean up.

    The marker is mandatory after P0-003: ``run_suite`` refuses to wipe a
    KG that isn't tagged as an eval instance. We set it for the duration
    of the test and clean both before and after so the fixture starts
    from an empty graph regardless of what other suites left behind.
    """
    monkeypatch.setenv("LABTFG_EVAL_KG", "1")
    await shared.init()
    if shared.kg is None:
        await shared.shutdown()
        pytest.skip("Neo4j not reachable")
    await shared.kg.query("MATCH (n) DETACH DELETE n")
    try:
        yield
    finally:
        try:
            await shared.kg.query("MATCH (n) DETACH DELETE n")
        finally:
            await shared.shutdown()


def _expected_paradigm_for(topic_text: str, expect: dict) -> tuple[str, ...]:
    """Pull the ``paradigm:`` slug from a topic's ``expect.research`` block.

    Returns ``("alpha",)`` as a default if the topic doesn't pin a slug —
    that way every fake pipeline result still carries something
    plausible, but topics with explicit expectations get the matching
    slug back from the stub so per-topic assertions pass identically on
    every run.
    """
    research = expect.get("research") or []
    for entry in research:
        if isinstance(entry, dict) and "paradigm" in entry:
            return (entry["paradigm"],)
    return ("alpha",)


def _make_stub_pipeline(spec: SuiteSpec):
    """Build a deterministic ``run_pipeline`` stub keyed by topic text.

    The stub reads the suite's per-topic expectation and synthesises a
    ``PipelineRunResult`` that satisfies it — paradigm slug, a tool
    call, and a single nodes_created tick so KG-growth assertions see
    activity. No randomness, so two invocations of the same suite must
    produce identical outcomes.
    """
    expectations: dict[str, dict] = {t.text: t.expect for t in spec.topics}

    async def _stub(topic, **kw):
        paradigms = _expected_paradigm_for(topic, expectations.get(topic, {}))
        return PipelineRunResult(
            run_id=f"det-{abs(hash(topic)) % 10**8:08d}",
            topic=topic,
            stages_run=(Stage.RESEARCH,),
            paradigms=paradigms,
            tool_call_log=(
                ToolCall(
                    name="retrieve_knowledge",
                    stage="researcher",
                    args_hash="stub",
                    succeeded=True,
                    duration_ms=50.0,
                ),
            ),
            memory_per_stage={
                "researcher": {
                    "nodes_created": 1,
                    "relations_created": 0,
                    "facts_stored": 0,
                }
            },
        )

    return _stub


def _outcome_signature(result) -> tuple:
    """Reduce a SuiteResult to (topic, stage, name, passed) tuples.

    ``detail`` strings can carry timing or counter values that aren't
    actually nondeterministic at the assertion-outcome level — comparing
    only ``passed`` flags keeps the determinism check focused on what
    P0-003 cares about: do the assertions agree across runs?
    """
    return tuple(
        (tr.topic, stage_name, outcome.name, outcome.passed)
        for tr in result.topic_results
        for stage_name, outcomes in tr.assertions.items()
        for outcome in outcomes
    )


def _suite_assertion_signature(result) -> tuple:
    return tuple((o.name, o.passed) for o in result.suite_assertions)


class TestSlugAccuracyDeterminism:
    @pytest.mark.asyncio
    async def test_back_to_back_runs_produce_identical_outcomes(
        self, live_eval_kg, tmp_path, monkeypatch
    ):
        # Run from the repo root so relative paths in slug-accuracy.yaml
        # (fixture_path: evals/fixtures/canonical-paradigms.json) resolve.
        monkeypatch.chdir(REPO_ROOT)

        spec = SuiteSpec.from_yaml(SLUG_ACCURACY_PATH)
        # Stop us from accidentally exhausting any real Anthropic budget.
        spec_no_budget = _drop_budget(spec)

        stub = _make_stub_pipeline(spec_no_budget)

        # Two fresh invocations sharing one process; the second run must
        # see the post-reset+post-seed KG state identical to the first.
        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=stub),
        ):
            first = await run_suite(
                spec_no_budget, client=AsyncMock(), search=AsyncMock()
            )
            second = await run_suite(
                spec_no_budget, client=AsyncMock(), search=AsyncMock()
            )

        assert first.error is None, first.error
        assert second.error is None, second.error

        first_sig = _outcome_signature(first)
        second_sig = _outcome_signature(second)
        assert first_sig == second_sig, (
            "slug-accuracy assertion outcomes drifted across runs:\n"
            f"  first:  {first_sig}\n  second: {second_sig}"
        )

        # Suite-level assertions must also match.
        assert _suite_assertion_signature(first) == _suite_assertion_signature(second)

        # Strength check: the determinism test would be vacuously true
        # if the stub silently produced two consistently-failing runs.
        # Require the per-topic assertions to actually pass — the stub
        # is meant to satisfy every ``paradigm:`` and ``tool_called:``
        # expectation, so any failure here means the stub or the suite
        # plumbing has drifted, not that determinism failed.
        passed_per_topic = sum(1 for *_, p in first_sig if p)
        assert passed_per_topic == len(first_sig), (
            "stub-driven assertions should all pass; "
            f"only {passed_per_topic}/{len(first_sig)} did.\n"
            f"signature: {first_sig}"
        )

        # KG node counts identical too — the reset+seed cycle is the
        # mechanism that makes the assertion outcomes stable, so a
        # divergence here means residue leaked between runs.
        assert first.post_stats is not None and second.post_stats is not None
        assert first.post_stats.total_nodes == second.post_stats.total_nodes, (
            f"KG node count drifted: first={first.post_stats.total_nodes} "
            f"vs second={second.post_stats.total_nodes}"
        )
        assert first.post_stats.by_label == second.post_stats.by_label

    @pytest.mark.asyncio
    async def test_canonical_paradigms_seeded_after_reset(
        self, live_eval_kg, tmp_path, monkeypatch
    ):
        """The setup block must land the 10 canonical Paradigm umbrellas."""
        monkeypatch.chdir(REPO_ROOT)
        spec = _drop_budget(SuiteSpec.from_yaml(SLUG_ACCURACY_PATH))

        async def _noop_stub(topic, **kw):
            return PipelineRunResult(
                run_id="seed-only",
                topic=topic,
                stages_run=(Stage.RESEARCH,),
                memory_per_stage={"researcher": {"nodes_created": 0}},
            )

        with patch(
            "decisionlab.eval.suite.run_pipeline",
            new=AsyncMock(side_effect=_noop_stub),
        ):
            result = await run_suite(spec, client=AsyncMock(), search=AsyncMock())

        assert result.error is None
        # Canonical fixture has 10 entries and the stub doesn't add any
        # paradigms, so post-stats must show ≥10 Paradigm nodes.
        assert result.post_stats is not None
        assert result.post_stats.by_label.get("Paradigm", 0) >= 10


def _drop_budget(spec: SuiteSpec) -> SuiteSpec:
    """Strip ``max_usd_total`` so the budget watchdog doesn't fire on the stub.

    The stub never bumps usage, so the watchdog is irrelevant — but the
    YAML's $12 cap is left in place for real runs. We clear it here so
    the deterministic path doesn't accidentally short-circuit on a
    cost-meter race condition with no real cost incurred.
    """
    from dataclasses import replace

    return replace(spec, max_usd_total=None)


def test_slug_accuracy_yaml_uses_reset_and_seed():
    """Static guard: the suite YAML must keep the determinism contract."""
    spec = SuiteSpec.from_yaml(SLUG_ACCURACY_PATH)
    assert spec.reset_kg_before is True, (
        "slug-accuracy.yaml must keep reset_kg_before: true (P0-003)"
    )
    seed_actions = [a for a in spec.setup if a.kind == "seed_canonical_paradigms"]
    assert seed_actions, (
        "slug-accuracy.yaml must declare a seed_canonical_paradigms setup action"
    )
    fixture = seed_actions[0].args.get("fixture_path")
    assert fixture and "canonical-paradigms" in str(fixture)
    assert os.path.exists(REPO_ROOT / fixture), (
        f"seed fixture path {fixture!r} does not exist relative to repo root"
    )
