"""CRAG fails closed: a Haiku grading error must mark every result
AMBIGUOUS (not CORRECT) so the routing layer either web-supplements
or downgrades trust, instead of silently passing through unchecked
results."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval import crag
from decisionlab.knowledge.retrieval.models import RetrievalResult


def _r(text: str) -> RetrievalResult:
    return RetrievalResult(text=text, score=0.5, source="dense", metadata={})


@pytest.mark.asyncio
async def test_grading_error_marks_results_ambiguous(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(side_effect=RuntimeError("haiku timeout"))

    out = await crag._classify_results(
        query="probe",
        task_context="ctx",
        results=[_r("a"), _r("b")],
        client=fake_client,
    )

    assert all(ev["classification"] == "AMBIGUOUS" for ev in out)
    assert all(0 <= ev["index"] < 2 for ev in out)


@pytest.mark.asyncio
async def test_grading_error_propagates_grading_failed_flag(monkeypatch):
    """The CRAGResult should expose grading_failed=True so the agent
    layer can attribute the AMBIGUOUS bucket to a model error rather
    than genuine ambiguity."""
    fake_client = MagicMock()
    fake_client.messages.create = AsyncMock(side_effect=RuntimeError("haiku timeout"))

    result = await crag.evaluate_results(
        query="probe",
        task_context="ctx",
        results=[_r("a"), _r("b")],
        client=fake_client,
    )

    assert result.grading_failed is True


@pytest.mark.asyncio
async def test_no_valid_evaluations_parsed_marks_ambiguous(monkeypatch):
    """If the response parses but no evaluations validate (e.g. all
    indices out of bounds), classify everything AMBIGUOUS — same
    fail-closed posture as a network error."""

    async def _bad_response(**_):
        block = MagicMock()
        block.type = "text"
        block.text = '{"evaluations": []}'
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        resp.usage = None
        return resp

    fake_client = MagicMock()
    fake_client.messages.create = _bad_response

    out = await crag._classify_results(
        query="probe", task_context="ctx", results=[_r("a")], client=fake_client
    )
    assert out[0]["classification"] == "AMBIGUOUS"
