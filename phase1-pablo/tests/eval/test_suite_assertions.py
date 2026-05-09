"""Suite-level predicate registry — predicates that need cross-topic
context to evaluate."""

from __future__ import annotations

import pytest

from decisionlab.eval.assertions import (
    AssertionOutcome,
    SuiteAssertionContext,
    register_suite,
    run_suite_assertion,
)


@pytest.mark.asyncio
async def test_register_and_dispatch_suite_predicate():
    @register_suite("dummy_count")
    async def _dummy(ctx: SuiteAssertionContext, args) -> AssertionOutcome:
        n = args["n"]
        return AssertionOutcome(
            name="dummy_count",
            passed=len(ctx.topic_results) >= n,
            detail=f"topics={len(ctx.topic_results)}",
        )

    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion({"dummy_count": {"n": 0}}, ctx)
    assert out.passed
    assert "topics=0" in out.detail


@pytest.mark.asyncio
async def test_unknown_suite_predicate_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion({"never_registered": {}}, ctx)
    assert not out.passed
    assert "unknown" in out.detail.lower()


@pytest.mark.asyncio
async def test_suite_yaml_parses_suite_assertions(tmp_path):
    """A suite YAML with a top-level ``suite_assertions:`` block parses
    them into ``SuiteSpec.suite_assertions``."""
    from decisionlab.eval.suite import SuiteSpec

    yaml_text = """
name: probe
stages: []
topics:
  - text: probe-only
suite_assertions:
  - always_pass: {}
"""
    path = tmp_path / "probe.yaml"
    path.write_text(yaml_text)
    spec = SuiteSpec.from_yaml(path)
    assert spec.suite_assertions == ({"always_pass": {}},)
    assert spec.stages == ()


@pytest.mark.asyncio
async def test_run_suite_executes_suite_assertions(tmp_path, monkeypatch):
    """run_suite collects outcomes from suite_assertions onto SuiteResult."""
    from unittest.mock import AsyncMock

    from decisionlab.eval.assertions import register_suite
    from decisionlab.eval.suite import SuiteSpec, run_suite

    @register_suite("hits_n")
    async def _hn(ctx, args) -> AssertionOutcome:
        n = args["n"]
        return AssertionOutcome(
            name="hits_n",
            passed=len(ctx.topic_results) == n,
            detail=f"n={len(ctx.topic_results)}",
        )

    yaml_text = """
name: probe-stages-empty
stages: []
topics:
  - text: probe-1
  - text: probe-2
suite_assertions:
  - hits_n: { n: 2 }
"""
    path = tmp_path / "probe.yaml"
    path.write_text(yaml_text)
    spec = SuiteSpec.from_yaml(path)

    # Avoid trying to insert run rows in postgres.
    monkeypatch.setattr(
        "decisionlab.eval.runner._create_run_row",
        AsyncMock(return_value=None),
    )

    from unittest.mock import MagicMock

    from shared.services import Services

    services = Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )
    client = AsyncMock()
    search = AsyncMock()
    result = await run_suite(
        spec, services=services, client=client, search=search, skip_kg_ops=True
    )
    assert len(result.suite_assertions) == 1
    assert result.suite_assertions[0].name == "hits_n"
    assert result.suite_assertions[0].passed
