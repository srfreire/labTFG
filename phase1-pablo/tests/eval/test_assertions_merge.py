"""merge_precision_recall: load fixture, call _verify_merge per
pair, compute precision/recall/F1 vs labels."""

from __future__ import annotations

import json

import pytest

from decisionlab.eval.assertions import (
    SuiteAssertionContext,
    run_suite_assertion,
)


def _structured_pair(
    candidate_name: str,
    existing_name: str,
    should_merge: bool,
    *,
    label: str = "Paradigm",
):
    """Build a fixture pair in the same shape as canonicalize-pairs.json."""
    return {
        "label": label,
        "candidate": {
            "name": candidate_name,
            "description": f"desc for {candidate_name}",
        },
        "existing": {"name": existing_name, "description": f"desc for {existing_name}"},
        "should_merge": should_merge,
    }


@pytest.fixture()
def fake_fixture(tmp_path):
    pairs = [
        _structured_pair("Q-learning", "Reinforcement Learning", True),
        _structured_pair("DDM", "Drift-diffusion model", True),
        _structured_pair("DDM", "Prospect theory", False),
        _structured_pair("reward", "value", False, label="Variable"),
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps({"pairs": pairs}))
    return path


@pytest.mark.asyncio
async def test_merge_pr_perfect_score(monkeypatch, fake_fixture):
    """Verifier always returns the labelled answer => precision=recall=1."""
    from decisionlab.canonicalize import _MergeVerification

    async def fake_verify(*, label, candidate_text, existing_text, similarity, client):
        # Use canonical names embedded in candidate_text to look up the pair.
        pairs = json.loads(fake_fixture.read_text())["pairs"]
        for p in pairs:
            if (
                p["candidate"]["name"] in candidate_text
                and p["existing"]["name"] in existing_text
            ):
                return _MergeVerification(merge=p["should_merge"], reason="oracle")
        raise AssertionError(f"unknown pair: {candidate_text} / {existing_text}")

    monkeypatch.setattr("decisionlab.canonicalize._verify_merge", fake_verify)

    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": str(fake_fixture),
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert out.passed, out.detail
    assert "precision=1.000" in out.detail
    assert "recall=1.000" in out.detail


@pytest.mark.asyncio
async def test_merge_pr_low_precision_fails(monkeypatch, fake_fixture):
    """Verifier always says merge => 2 TP, 2 FP => precision=0.5."""
    from decisionlab.canonicalize import _MergeVerification

    async def always_merge(**_kw):
        return _MergeVerification(merge=True, reason="always")

    monkeypatch.setattr("decisionlab.canonicalize._verify_merge", always_merge)

    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": str(fake_fixture),
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert not out.passed
    assert "precision=0.500" in out.detail


@pytest.mark.asyncio
async def test_merge_pr_missing_fixture_fails_cleanly():
    ctx = SuiteAssertionContext(
        suite=None, topic_results=(), pre_stats=None, post_stats=None
    )
    out = await run_suite_assertion(
        {
            "merge_precision_recall": {
                "fixture": "/nonexistent.json",
                "min_precision": 0.95,
                "min_recall": 0.90,
            }
        },
        ctx,
    )
    assert not out.passed
    assert "fixture" in out.detail.lower()
