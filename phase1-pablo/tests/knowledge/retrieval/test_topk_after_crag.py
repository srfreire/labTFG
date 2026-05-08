"""When CRAG injects web supplements, the final output should not be
silently truncated back to ``top_k`` mid-process — that would discard
the supplements that CRAG specifically requested.

Truncation only happens at the agent boundary, and the cap stretches
to ``2 * top_k`` when CRAG added a web supplement so the agent gets
both the kept stored hits and the fresh web ones.
"""

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.tool import _final_truncate


def _r(text: str) -> RetrievalResult:
    return RetrievalResult(text=text, score=0.5, source="dense", metadata={})


def test_no_web_supplement_truncates_to_top_k():
    results = [_r(f"r{i}") for i in range(10)]
    out = _final_truncate(results, top_k=5, web_supplemented=False)
    assert len(out) == 5


def test_web_supplemented_results_allowed_up_to_2x_top_k():
    results = [_r(f"r{i}") for i in range(10)]
    out = _final_truncate(results, top_k=5, web_supplemented=True)
    assert len(out) == 10  # all kept, capped at 2 * top_k = 10


def test_web_supplemented_below_cap_returns_all():
    """When the supplemented set is already smaller than 2*top_k, no
    truncation happens — return everything."""
    results = [_r(f"r{i}") for i in range(7)]
    out = _final_truncate(results, top_k=5, web_supplemented=True)
    assert len(out) == 7


def test_empty_results_returns_empty():
    out = _final_truncate([], top_k=5, web_supplemented=True)
    assert out == []
