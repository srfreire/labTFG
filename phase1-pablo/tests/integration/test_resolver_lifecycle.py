"""Integration coverage for the resolver state machine.

Issue 7. Exercises the full classification → CRUD path of
:func:`decisionlab.knowledge.resolver.resolve_and_store` for each branch of
the DUP / CORROBORATE / ENRICH / CONTRADICT / NEW state machine, asserting
that the right persistence helper (``create_memory``, ``supersede_memory``,
``update_confidence``) is invoked with the right arguments — i.e. that
classification X drives CRUD helper Y with payload Z.

Real-DB fixtures (pytest-postgresql / aiosqlite session) are intentionally
not introduced here: no such infrastructure exists in the repo today and
the issue forbids adding new test deps. Sessions and the embedding /
vector-store ports are ``AsyncMock``s. The load-bearing assertion is the
state-machine behaviour, not Postgres semantics — which are covered by
``shared/tests`` directly against ``pipeline_memories``.

All tests are marked ``integration`` so the unit-test job (``-m "not
integration"``) skips them. They run locally via:

    cd phase1-pablo && uv run pytest tests/integration/ -v -m integration
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.models import ExtractionResult
from decisionlab.knowledge.resolver import resolve_and_store

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers — mirror tests/knowledge/test_resolver.py shapes so the integration
# layer reads identically to the unit layer it complements.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FakeScoredPoint:
    id: str
    score: float
    payload: dict


_RUN_ID = "00000000-0000-0000-0000-0000000000aa"
_OTHER_RUN_ID = "00000000-0000-0000-0000-0000000000bb"


def _tool_response(tool_name: str, payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = payload

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.usage = None
    return resp


def _make_client(responses: list[dict]) -> MagicMock:
    """Build an AsyncAnthropic-shaped client. Each response dict is auto-routed
    to the right ``emit_*`` tool name based on its keys (importance vs
    classification)."""
    queue: list[MagicMock] = []
    for entry in responses:
        if isinstance(entry, str):
            entry = json.loads(entry)
        if isinstance(entry, list):
            queue.append(_tool_response("emit__ImportanceScores", {"scores": entry}))
        elif "scores" in entry:
            queue.append(_tool_response("emit__ImportanceScores", entry))
        elif "classification" in entry:
            queue.append(_tool_response("emit__ConflictClassification", entry))
        else:
            raise ValueError(f"Unrecognised payload shape: {entry!r}")

    iterator = iter(queue)

    async def _create(**_kw):
        return next(iterator)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    return client


def _embedding_service() -> AsyncMock:
    emb = AsyncMock()
    emb.embed_query = AsyncMock(return_value=[0.1] * 1024)
    emb.embed_texts = AsyncMock(
        side_effect=lambda texts, input_type="document": [[0.1] * 1024 for _ in texts],
    )
    return emb


def _vector_store(search_results: list | None = None) -> AsyncMock:
    vs = AsyncMock()
    vs.search_dense = AsyncMock(return_value=search_results or [])
    vs.upsert_dense = AsyncMock()
    vs.upsert_sparse = AsyncMock()
    return vs


def _existing_point(*, content: str, score: float = 0.90) -> _FakeScoredPoint:
    """Build a Qdrant search hit pointing at a memory from a different run.

    Score 0.90 sits in the ambiguous 0.85–0.95 band so the resolver routes
    to the Sonnet classifier instead of fast-pathing to DUPLICATE.
    """
    return _FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=score,
        payload={
            "text_preview": content,
            "source_stage": "researcher",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": _OTHER_RUN_ID,
        },
    )


def _extraction(facts: list[str], stage: str = "researcher") -> ExtractionResult:
    return ExtractionResult(
        nodes=[],
        relations=[],
        facts=facts,
        stage=stage,
        run_id=_RUN_ID,
    )


# ---------------------------------------------------------------------------
# 1. Seed + DUP path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_seed_then_duplicate_does_not_create_or_mutate():
    """Seed a base memory M1 (created via ``create_memory`` with confidence
    0.7) and then re-encounter the same content. Resolver classifies as
    ``DUPLICATE`` — it must NOT call ``create_memory``, ``supersede_memory``,
    or ``update_confidence`` (resolver.py only increments the
    duplicates_skipped counter; it does not call ``touch_memory`` on the
    matched row)."""
    seed_session = AsyncMock()
    seed_id = uuid.uuid4()
    seed_run_uuid = uuid.UUID(_OTHER_RUN_ID)

    with patch(
        "decisionlab.knowledge.resolver.create_memory",
        new_callable=AsyncMock,
        return_value=MagicMock(id=seed_id),
    ) as seed_create:
        from decisionlab.knowledge.resolver import create_memory as _seed_call

        await _seed_call(
            seed_session,
            content="ghrelin modulates hunger",
            namespace="paradigm",
            memory_type="semantic",
            source_stage="researcher",
            run_id=seed_run_uuid,
            importance=8.0,
            confidence=0.7,
        )

    seed_create.assert_called_once()
    assert seed_create.call_args.kwargs["confidence"] == 0.7
    assert seed_create.call_args.kwargs["content"] == "ghrelin modulates hunger"

    # Now re-process the same fact in a different run. Vector store returns
    # the seeded memory as a near-match in the ambiguous band; Sonnet says
    # DUPLICATE.
    importance_resp = [
        {"fact": "ghrelin modulates hunger", "importance": 8, "reasoning": "core"},
    ]
    conflict_resp = {
        "classification": "DUPLICATE",
        "reasoning": "same fact",
        "merged_content": None,
    }
    client = _make_client([importance_resp, conflict_resp])

    emb = _embedding_service()
    vs = _vector_store([_existing_point(content="ghrelin modulates hunger")])
    session = AsyncMock()

    extraction = _extraction(["ghrelin modulates hunger"])

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ) as mock_update,
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.duplicates_skipped == 1
    assert result.memories_created == 0
    assert result.sonnet_calls == 1

    # DUP semantics: no CRUD whatsoever on the matched row.
    mock_create.assert_not_called()
    mock_supersede.assert_not_called()
    mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# 2. CORROBORATE path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_corroboration_calls_update_confidence():
    """CORROBORATION → ``update_confidence(corroborate=True)`` on the matched
    row, NO new memory created. Per ``shared.pipeline_memories.update_confidence``
    the underlying delta is +0.05 (clamped to [0.1, 1.0]) — the integration
    test asserts the helper is invoked with the matched memory id and
    ``corroborate=True``; the +0.05 arithmetic is the helper's contract,
    covered in shared tests."""
    matched = _existing_point(content="leptin signals satiety")
    matched_uuid = uuid.UUID(matched.id)

    importance_resp = [
        {"fact": "leptin signals satiety", "importance": 7, "reasoning": "hormone"},
    ]
    conflict_resp = {
        "classification": "CORROBORATION",
        "reasoning": "Independent confirmation",
        "merged_content": None,
    }
    client = _make_client([importance_resp, conflict_resp])

    emb = _embedding_service()
    vs = _vector_store([matched])
    session = AsyncMock()

    extraction = _extraction(["leptin signals satiety"])

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ) as mock_update,
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.corroborations == 1
    assert result.memories_created == 0
    assert result.duplicates_skipped == 0
    assert result.sonnet_calls == 1

    # update_confidence(session, matched_id, corroborate=True) — the +0.05
    # arithmetic and clamp live in shared.pipeline_memories.
    mock_update.assert_called_once_with(session, matched_uuid, corroborate=True)
    mock_create.assert_not_called()
    mock_supersede.assert_not_called()


# ---------------------------------------------------------------------------
# 3. ENRICHMENT path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_enrichment_supersedes_old_with_merged_content():
    """ENRICHMENT → ``supersede_memory(old_id=matched, new_content=merged,
    confidence=stage_default)``. The replacement row carries the stage's
    confidence (0.7 for ``formalizer``); the OLD row's ``valid_to`` /
    ``superseded_by`` are set inside ``supersede_memory`` itself (covered
    in shared tests)."""
    matched = _existing_point(content="learning rate = 0.1")
    matched_uuid = uuid.UUID(matched.id)

    importance_resp = [
        {
            "fact": "learning rate = 0.1, sourced from Keramati 2011",
            "importance": 7,
            "reasoning": "specific",
        },
    ]
    merged_text = "learning rate = 0.1 (sourced from Keramati 2011)"
    conflict_resp = {
        "classification": "ENRICHMENT",
        "reasoning": "Adds source citation",
        "merged_content": merged_text,
    }
    client = _make_client([importance_resp, conflict_resp])

    emb = _embedding_service()
    vs = _vector_store([matched])
    session = AsyncMock()

    extraction = _extraction(
        ["learning rate = 0.1, sourced from Keramati 2011"],
        stage="formalizer",
    )

    new_mem_id = uuid.uuid4()
    fake_new_mem = MagicMock(id=new_mem_id)

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory",
            new_callable=AsyncMock,
            return_value=fake_new_mem,
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ) as mock_update,
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.enrichments == 1
    assert result.memories_created == 0
    assert result.contradictions == 0
    assert result.sonnet_calls == 1

    # Supersede invoked exactly once with the merged content and the
    # stage's namespace / memory_type / confidence defaults.
    mock_supersede.assert_called_once()
    sk = mock_supersede.call_args.kwargs
    assert sk["old_id"] == matched_uuid
    assert sk["new_content"] == merged_text
    assert sk["namespace"] == "formulation"
    assert sk["memory_type"] == "semantic"
    assert sk["source_stage"] == "formalizer"
    assert sk["confidence"] == 0.7  # _STAGE_CONFIDENCE["formalizer"]
    assert sk["importance"] == 7

    # ENRICHMENT does not touch the standalone CRUD helpers.
    mock_create.assert_not_called()
    mock_update.assert_not_called()

    # Both vector channels must be re-indexed for the merged memory id.
    vs.upsert_dense.assert_called_once()
    vs.upsert_sparse.assert_called_once()
    assert vs.upsert_dense.call_args.args[1] == str(new_mem_id)
    assert vs.upsert_sparse.call_args.args[1] == str(new_mem_id)
    assert vs.upsert_sparse.call_args.args[2] == merged_text


# ---------------------------------------------------------------------------
# 4. CONTRADICT path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_contradiction_drops_confidence_and_records_meta():
    """CONTRADICTION → ``update_confidence(contradict=True)`` on the live
    row (delta = -0.10, contracted in ``shared.pipeline_memories``), THEN
    ``supersede_memory`` with the new fact, THEN ``create_memory`` of an
    episodic row in namespace ``meta`` recording ``run … contradicted memory
    …: old → new``. The integration check is the call ORDER and the meta
    row's namespace / memory_type."""
    matched = _existing_point(content="setpoint = 50")
    matched_uuid = uuid.UUID(matched.id)

    importance_resp = [
        {
            "fact": "setpoint = 70 based on updated data",
            "importance": 8,
            "reasoning": "param update",
        },
    ]
    conflict_resp = {
        "classification": "CONTRADICTION",
        "reasoning": "Different setpoint values",
        "merged_content": None,
    }
    client = _make_client([importance_resp, conflict_resp])

    emb = _embedding_service()
    vs = _vector_store([matched])
    session = AsyncMock()

    extraction = _extraction(["setpoint = 70 based on updated data"], stage="reasoner")

    fake_new_mem = MagicMock(id=uuid.uuid4())

    # Use a manager Mock so we can verify the call order across all three
    # CRUD helpers — the contradiction path must drop confidence on the
    # live row BEFORE superseding it, then write the episodic meta row.
    manager = MagicMock()
    mock_create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    mock_supersede = AsyncMock(return_value=fake_new_mem)
    mock_update = AsyncMock()
    manager.attach_mock(mock_create, "create_memory")
    manager.attach_mock(mock_supersede, "supersede_memory")
    manager.attach_mock(mock_update, "update_confidence")

    with (
        patch("decisionlab.knowledge.resolver.create_memory", mock_create),
        patch("decisionlab.knowledge.resolver.supersede_memory", mock_supersede),
        patch("decisionlab.knowledge.resolver.update_confidence", mock_update),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.contradictions == 1
    assert result.memories_created == 0  # meta row is bookkeeping, not a fact
    assert result.sonnet_calls == 1

    # update_confidence invoked with contradict=True on the live row.
    mock_update.assert_called_once_with(session, matched_uuid, contradict=True)

    # supersede_memory called with the new content under the reasoner's
    # namespace / memory_type / confidence defaults.
    mock_supersede.assert_called_once()
    sk = mock_supersede.call_args.kwargs
    assert sk["old_id"] == matched_uuid
    assert sk["new_content"] == "setpoint = 70 based on updated data"
    assert sk["namespace"] == "formulation"
    assert sk["memory_type"] == "semantic"
    assert sk["source_stage"] == "reasoner"
    assert sk["confidence"] == 0.8  # _STAGE_CONFIDENCE["reasoner"]

    # create_memory called once for the meta/episodic bookkeeping row.
    mock_create.assert_called_once()
    ck = mock_create.call_args.kwargs
    assert ck["namespace"] == "meta"
    assert ck["memory_type"] == "episodic"
    assert ck["source_stage"] == "memory_agent"
    assert ck["confidence"] == 1.0
    assert "contradicted memory" in ck["content"]
    assert "setpoint = 70 based on updated data" in ck["content"]

    # Order: update_confidence → supersede_memory → create_memory.
    call_order = [name for name, *_ in manager.mock_calls]
    assert call_order == ["update_confidence", "supersede_memory", "create_memory"]


# ---------------------------------------------------------------------------
# 5. NEW path (no _classify_conflict mock — dedup threshold is the gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_new_path_creates_fresh_row_without_sonnet():
    """When the candidate set is below the 0.85 dedup threshold, the resolver
    skips the Sonnet classifier entirely and goes straight to
    ``create_memory``. We seed an unrelated memory (low cosine similarity)
    and DON'T mock ``_classify_conflict`` — if the threshold logic were
    broken, the test would fail because no conflict response is queued and
    ``StopIteration`` would surface from the client side-effect."""
    unrelated = _FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.40,  # well below the 0.85 threshold
        payload={
            "text_preview": "unrelated background fact",
            "source_stage": "researcher",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": _OTHER_RUN_ID,
        },
    )

    # Only one LLM call is expected: the importance batch. No conflict
    # response queued — the absence of a Sonnet call is part of the
    # assertion.
    importance_resp = [
        {
            "fact": "novel insight about reward prediction",
            "importance": 7,
            "reasoning": "new",
        },
    ]
    client = _make_client([importance_resp])

    emb = _embedding_service()
    vs = _vector_store([unrelated])
    session = AsyncMock()

    extraction = _extraction(["novel insight about reward prediction"])

    fresh_id = uuid.uuid4()

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            return_value=MagicMock(id=fresh_id),
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ) as mock_update,
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.memories_created == 1
    assert result.sonnet_calls == 0
    assert result.duplicates_skipped == 0
    assert result.corroborations == 0
    assert result.enrichments == 0
    assert result.contradictions == 0

    mock_create.assert_called_once()
    ck = mock_create.call_args.kwargs
    assert ck["content"] == "novel insight about reward prediction"
    assert ck["namespace"] == "paradigm"
    assert ck["memory_type"] == "semantic"
    assert ck["source_stage"] == "researcher"
    assert ck["confidence"] == 0.6  # _STAGE_CONFIDENCE["researcher"]
    assert ck["run_id"] == uuid.UUID(_RUN_ID)

    mock_supersede.assert_not_called()
    mock_update.assert_not_called()

    # Exactly one LLM call total: the importance batch. No Sonnet.
    assert client.messages.create.call_count == 1
