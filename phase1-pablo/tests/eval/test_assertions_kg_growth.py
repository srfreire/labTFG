"""kg_growth_rate: per-label delta divided by topic count, fail above
max_per_topic. Pre/post stats come in via SuiteAssertionContext."""

from dataclasses import dataclass, field

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import TopicResult


@dataclass(frozen=True)
class _FakeStats:
    by_label: dict[str, int] = field(default_factory=dict)


def _tr(topic):
    return TopicResult(
        topic=topic,
        run=PipelineRunResult(run_id="r", topic=topic, stages_run=("research",)),
        assertions={},
    )


@pytest.mark.asyncio
async def test_kg_growth_rate_under_threshold_passes():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"), _tr("b"), _tr("c"), _tr("d")),  # 4 topics
        pre_stats=_FakeStats(by_label={"Paradigm": 10}),
        post_stats=_FakeStats(by_label={"Paradigm": 14}),  # +4 / 4 = 1.0
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Paradigm", "max_per_topic": 1.5}}, ctx
    )
    assert out.passed, out.detail
    assert "1.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_over_threshold_fails():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"), _tr("b")),  # 2 topics
        pre_stats=_FakeStats(by_label={"Variable": 5}),
        post_stats=_FakeStats(by_label={"Variable": 25}),  # +20 / 2 = 10.0
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Variable", "max_per_topic": 6}}, ctx
    )
    assert not out.passed
    assert "10.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_unknown_label_treated_as_zero():
    """If the label has no entry pre or post, growth = 0 — passes."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"),),
        pre_stats=_FakeStats(by_label={}),
        post_stats=_FakeStats(by_label={}),
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Phantom", "max_per_topic": 0.5}}, ctx
    )
    assert out.passed
    assert "0.00" in out.detail


@pytest.mark.asyncio
async def test_kg_growth_rate_no_stats_fails_visibly():
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(_tr("a"),),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"kg_growth_rate": {"label": "Paradigm", "max_per_topic": 1.5}}, ctx
    )
    assert not out.passed
    assert "stats" in out.detail.lower()
