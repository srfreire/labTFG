"""slug_hit_rate: sum hits across topics, fail if rate below min_rate.
Liberal matching — canonical slug counts if it appears anywhere in
result.paradigms (not just position 0)."""

import json

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.suite import TopicResult


def _tr(topic_text: str, paradigms: tuple[str, ...]) -> TopicResult:
    run = PipelineRunResult(
        run_id="r",
        topic=topic_text,
        stages_run=("research",),
        paradigms=paradigms,
    )
    return TopicResult(topic=topic_text, run=run, assertions={})


@pytest.fixture()
def fixture_path(tmp_path):
    pairs = [
        {"topic_text": "RL question", "expected_slug": "reinforcement-learning"},
        {"topic_text": "loss aversion ?", "expected_slug": "prospect-theory"},
        {"topic_text": "DDM speed acc", "expected_slug": "drift-diffusion-model"},
        {"topic_text": "free energy ?", "expected_slug": "free-energy-principle"},
    ]
    p = tmp_path / "oracle.json"
    p.write_text(json.dumps(pairs))
    return p


@pytest.mark.asyncio
async def test_slug_hit_rate_passes_on_full_hits(fixture_path):
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question", ("reinforcement-learning",)),
            _tr("loss aversion ?", ("prospect-theory", "regret")),
            _tr("DDM speed acc", ("drift-diffusion-model",)),
            _tr("free energy ?", ("free-energy-principle", "active-inference")),
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 0.8}}, ctx
    )
    assert out.passed, out.detail
    assert "4/4" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_liberal_match_counts_position_n(fixture_path):
    """The canonical slug appears at position 1, not 0 — still a hit."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question", ("exploration-exploitation", "reinforcement-learning")),
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 1.0}}, ctx
    )
    assert "1/1" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_fails_below_threshold(fixture_path):
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question", ("reinforcement-learning",)),  # hit
            _tr("loss aversion ?", ("regret-theory",)),  # miss
            _tr("DDM speed acc", ("drift-diffusion-model",)),  # hit
            _tr("free energy ?", ("predictive-coding",)),  # miss
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 0.8}}, ctx
    )
    assert not out.passed
    assert "2/4" in out.detail or "0.500" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_topic_not_in_oracle_skipped(fixture_path):
    """Topics not present in the oracle are not penalized; they're just
    not counted toward the denominator."""
    ctx = SuiteAssertionContext(
        suite=None,
        topic_results=(
            _tr("RL question", ("reinforcement-learning",)),
            _tr("unrelated topic", ("something",)),  # not in oracle
        ),
        pre_stats=None,
        post_stats=None,
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": str(fixture_path), "min_rate": 1.0}}, ctx
    )
    assert "1/1" in out.detail


@pytest.mark.asyncio
async def test_slug_hit_rate_missing_oracle_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {"slug_hit_rate": {"oracle": "/nonexistent.json", "min_rate": 0.8}}, ctx
    )
    assert not out.passed
    assert "oracle" in out.detail.lower()
