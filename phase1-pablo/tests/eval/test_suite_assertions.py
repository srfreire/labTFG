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
