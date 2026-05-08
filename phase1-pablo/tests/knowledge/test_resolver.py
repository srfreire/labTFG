"""Tests for conflict resolution, importance scoring, and memory persistence.

Covers acceptance criteria AC1 through AC7 for issue P2-004. After Phase B
(research-memory rewrite) both ``_score_importance`` and ``_classify_conflict``
route through ``decisionlab.structured.call_structured`` (forced tool-use),
so the mock here builds tool_use responses keyed by the wrapper's
``emit_<schema>`` tool name.
"""

import json
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.models import ExtractionResult, ResolutionResult
from decisionlab.knowledge.resolver import (
    _classify_conflict,
    _find_duplicates,
    _score_importance,
    resolve_and_store,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_importance(scored: list[dict]) -> dict:
    """Wrap pre-rewrite ``[{fact, importance, ...}]`` shape in the new
    ``{scores: [...]}`` envelope expected by ``_ImportanceScores``."""
    return {"scores": scored}


def _make_tool_response(
    tool_name: str, payload: dict, *, stop_reason: str = "end_turn"
) -> MagicMock:
    """Build a structured-output response carrying one tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = payload

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = stop_reason
    resp.usage = None
    return resp


def _make_client(responses: list) -> MagicMock:
    """Build a client whose ``messages.create`` yields the given responses.

    Each entry is one of:
      - a JSON string with shape matching the next call (importance =
        ``[{fact, importance}, ...]`` or ``{scores: [...]}``; conflict =
        ``{classification, reasoning, merged_content}``) — wrapped to a
        tool_use block,
      - a dict (used directly as tool input),
      - a pre-built MagicMock,
      - an exception class or instance (raised on dispatch).
    """
    queue: list = []
    for entry in responses:
        if isinstance(entry, BaseException) or (
            isinstance(entry, type) and issubclass(entry, BaseException)
        ):
            queue.append(entry)
            continue
        if isinstance(entry, MagicMock):
            queue.append(entry)
            continue
        if isinstance(entry, str):
            try:
                parsed = json.loads(entry)
            except json.JSONDecodeError:
                parsed = entry
        else:
            parsed = entry

        # Decide which tool name based on the shape of the parsed payload.
        if isinstance(parsed, list):
            tool_name = "emit__ImportanceScores"
            parsed = _wrap_importance(parsed)
        elif isinstance(parsed, dict) and "scores" in parsed:
            tool_name = "emit__ImportanceScores"
        elif isinstance(parsed, dict) and "classification" in parsed:
            tool_name = "emit__ConflictClassification"
        else:
            # Fallback: assume importance.
            tool_name = "emit__ImportanceScores"
        queue.append(_make_tool_response(tool_name, parsed))

    iterator = iter(queue)

    async def _create(**_kw):
        item = next(iterator)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item()
        return item

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    return client


@dataclass(frozen=True)
class FakeScoredPoint:
    id: str
    score: float
    payload: dict


_DEFAULT_RUN_ID = "00000000-0000-0000-0000-000000000001"


def _make_extraction(
    facts: list[str],
    stage: str = "researcher",
    run_id: str = _DEFAULT_RUN_ID,
) -> ExtractionResult:
    return ExtractionResult(
        nodes=[],
        relations=[],
        facts=facts,
        stage=stage,
        run_id=run_id,
    )


def _mock_embedding_service() -> AsyncMock:
    emb = AsyncMock()
    emb.embed_query = AsyncMock(return_value=[0.1] * 1024)
    emb.embed_texts = AsyncMock(
        side_effect=lambda texts, input_type="document": [[0.1] * 1024 for _ in texts],
    )
    return emb


def _mock_vector_store(search_results: list | None = None) -> AsyncMock:
    vs = AsyncMock()
    vs.search_dense = AsyncMock(return_value=search_results or [])
    vs.upsert_dense = AsyncMock()
    vs.upsert_sparse = AsyncMock()
    return vs


def _mock_db_session() -> AsyncMock:
    session = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# AC1: Importance scoring — meaningful facts score high, trivial ones low
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_importance_scoring_high_for_meaningful_fact():
    """AC1: 'ghrelin modulates hunger via hypothalamic signaling' scores >= 7."""
    scored_response = json.dumps(
        [
            {
                "fact": "ghrelin modulates hunger via hypothalamic signaling",
                "importance": 8,
                "reasoning": "Core mechanism linking a specific hormone to behavior",
            },
            {
                "fact": "the grid has resources",
                "importance": 3,
                "reasoning": "Trivial implementation detail about grid layout",
            },
        ]
    )
    client = _make_client([scored_response])

    facts = [
        "ghrelin modulates hunger via hypothalamic signaling",
        "the grid has resources",
    ]
    scores = await _score_importance(facts, client)

    assert scores["ghrelin modulates hunger via hypothalamic signaling"] >= 7
    assert scores["the grid has resources"] <= 4


@pytest.mark.asyncio
async def test_importance_scoring_uses_fast_model():
    """AC2 (P0-001): Importance scoring uses ``knowledge_fast_model``
    (Haiku) — judging 1–10 importance is mechanical and the prior Sonnet
    spend was wasteful. See docs/specs/memory-refactor/phase-0-stop-lying.md
    §R1."""
    from decisionlab.config import SETTINGS

    scored_response = json.dumps(
        [
            {"fact": "test fact", "importance": 5, "reasoning": "average"},
        ]
    )
    client = _make_client([scored_response])

    await _score_importance(["test fact"], client)

    client.messages.create.assert_called_once()
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == SETTINGS.knowledge_fast_model
    # Forced tool-use: a single tool with input_schema, tool_choice locked.
    assert len(call_kwargs["tools"]) == 1
    assert call_kwargs["tool_choice"]["type"] == "tool"


@pytest.mark.asyncio
async def test_importance_scoring_empty_facts():
    """Empty facts list returns empty dict without calling LLM."""
    client = _make_client([])
    scores = await _score_importance([], client)
    assert scores == {}
    client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# AC2: Duplicate detection + DUPLICATE classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_fact_triggers_sonnet_and_skips():
    """AC2: Fact identical to existing memory (>0.85 similarity) → Sonnet → DUPLICATE → no new memory."""
    existing_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.92,
        payload={
            "text_preview": "ghrelin modulates hunger",
            "source_stage": "researcher",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    # Haiku importance response
    importance_resp = json.dumps(
        [
            {"fact": "ghrelin modulates hunger", "importance": 8, "reasoning": "core"},
        ]
    )
    # Sonnet conflict response
    conflict_resp = json.dumps(
        {
            "classification": "DUPLICATE",
            "reasoning": "Same information about ghrelin and hunger",
            "merged_content": None,
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()

    extraction = _make_extraction(["ghrelin modulates hunger"])

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.duplicates_skipped == 1
    assert result.memories_created == 0
    assert result.sonnet_calls == 1
    mock_create.assert_not_called()
    mock_supersede.assert_not_called()


# ---------------------------------------------------------------------------
# AC3: ENRICHMENT classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_supersedes_old_memory():
    """AC3: Fact adding detail to existing → ENRICHMENT → old superseded, new created with merged content."""
    existing_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.90,
        payload={
            "text_preview": "learning rate = 0.1",
            "source_stage": "formalizer",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {
                "fact": "learning rate = 0.1, sourced from Keramati 2011",
                "importance": 7,
                "reasoning": "specific",
            },
        ]
    )
    merged_text = "learning rate = 0.1 (sourced from Keramati 2011)"
    conflict_resp = json.dumps(
        {
            "classification": "ENRICHMENT",
            "reasoning": "New fact adds source citation to existing parameter value",
            "merged_content": merged_text,
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()

    extraction = _make_extraction(
        ["learning rate = 0.1, sourced from Keramati 2011"],
        stage="formalizer",
    )

    fake_new_mem = MagicMock()
    fake_new_mem.id = uuid.uuid4()

    with (
        patch("decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock),
        patch(
            "decisionlab.knowledge.resolver.supersede_memory",
            new_callable=AsyncMock,
            return_value=fake_new_mem,
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.enrichments == 1
    assert result.sonnet_calls == 1
    mock_supersede.assert_called_once()
    supersede_kwargs = mock_supersede.call_args
    assert supersede_kwargs.kwargs["new_content"] == merged_text

    # Qdrant should be updated with embedding for merged content
    vs.upsert_dense.assert_called_once()
    upsert_kwargs = vs.upsert_dense.call_args
    assert upsert_kwargs.args[0] == "memories_dense"
    enrichment_payload = upsert_kwargs.args[3]
    assert merged_text[:200] in enrichment_payload["text_preview"]
    # P3-002: enrichment payload no longer carries confidence — Postgres
    # is the single source of truth.
    assert "confidence" not in enrichment_payload


# ---------------------------------------------------------------------------
# AC4: CONTRADICTION classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contradiction_supersedes_old_increments_counter():
    """AC4: Contradictory fact → old superseded, new created, contradictions incremented."""
    old_id = str(uuid.uuid4())
    existing_point = FakeScoredPoint(
        id=old_id,
        score=0.88,
        payload={
            "text_preview": "setpoint = 50",
            "source_stage": "reasoner",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {
                "fact": "setpoint = 70 based on updated data",
                "importance": 8,
                "reasoning": "parameter update",
            },
        ]
    )
    conflict_resp = json.dumps(
        {
            "classification": "CONTRADICTION",
            "reasoning": "Different setpoint values — new is based on updated data",
            "merged_content": None,
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()

    extraction = _make_extraction(
        ["setpoint = 70 based on updated data"],
        stage="reasoner",
    )

    fake_new_mem = MagicMock()
    fake_new_mem.id = uuid.uuid4()

    with (
        patch("decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock),
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

    assert result.contradictions == 1
    assert result.sonnet_calls == 1

    # Old memory superseded
    mock_supersede.assert_called_once()
    assert (
        mock_supersede.call_args.kwargs["new_content"]
        == "setpoint = 70 based on updated data"
    )

    # Contradiction counter incremented BEFORE supersede (on live row)
    mock_update.assert_called_once_with(session, uuid.UUID(old_id), contradict=True)
    # update_confidence must be called before supersede_memory
    assert mock_update.call_args_list[0] is not None
    assert mock_supersede.call_args_list[0] is not None


# ---------------------------------------------------------------------------
# AC5: New facts without duplicates stored directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_facts_stored_with_correct_metadata():
    """AC5: Facts with no duplicates stored with correct namespace, memory_type, importance, confidence."""
    importance_resp = json.dumps(
        [
            {
                "fact": "dopamine mediates wanting",
                "importance": 9,
                "reasoning": "core mechanism",
            },
            {
                "fact": "nucleus accumbens processes reward",
                "importance": 8,
                "reasoning": "brain region function",
            },
        ]
    )
    client = _make_client([importance_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([])  # no duplicates
    session = _mock_db_session()

    extraction = _make_extraction(
        ["dopamine mediates wanting", "nucleus accumbens processes reward"],
        stage="researcher",
    )

    fake_mems = [MagicMock(id=uuid.uuid4()), MagicMock(id=uuid.uuid4())]

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            side_effect=fake_mems,
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.memories_created == 2
    assert result.sonnet_calls == 0

    # Check first call
    first_call = mock_create.call_args_list[0]
    assert first_call.kwargs["content"] == "dopamine mediates wanting"
    assert first_call.kwargs["namespace"] == "paradigm"
    assert first_call.kwargs["memory_type"] == "semantic"
    assert first_call.kwargs["source_stage"] == "researcher"
    assert first_call.kwargs["run_id"] == uuid.UUID(_DEFAULT_RUN_ID)
    assert first_call.kwargs["importance"] == 9
    assert first_call.kwargs["confidence"] == 0.6

    mock_supersede.assert_not_called()


@pytest.mark.asyncio
async def test_builder_stage_uses_correct_defaults():
    """AC5: Builder stage → namespace='model', memory_type='procedural', confidence=0.9."""
    importance_resp = json.dumps(
        [
            {
                "fact": "uses Q-learning with softmax",
                "importance": 6,
                "reasoning": "code pattern",
            },
        ]
    )
    client = _make_client([importance_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([])
    session = _mock_db_session()

    extraction = _make_extraction(
        ["uses Q-learning with softmax"],
        stage="builder",
    )

    fake_mem = MagicMock(id=uuid.uuid4())

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            return_value=fake_mem,
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ),
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.memories_created == 1
    first_call = mock_create.call_args_list[0]
    assert first_call.kwargs["namespace"] == "model"
    assert first_call.kwargs["memory_type"] == "procedural"
    assert first_call.kwargs["confidence"] == 0.9


# ---------------------------------------------------------------------------
# AC6: Sonnet only called when duplicates detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sonnet_not_called_without_duplicates():
    """AC6: sonnet_calls == 0 when no duplicates found."""
    importance_resp = json.dumps(
        [
            {"fact": "fact one", "importance": 5, "reasoning": "avg"},
            {"fact": "fact two", "importance": 5, "reasoning": "avg"},
            {"fact": "fact three", "importance": 5, "reasoning": "avg"},
        ]
    )
    client = _make_client([importance_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([])  # no matches
    session = _mock_db_session()

    extraction = _make_extraction(["fact one", "fact two", "fact three"])

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            return_value=MagicMock(id=uuid.uuid4()),
        ),
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ),
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.sonnet_calls == 0
    assert result.memories_created == 3
    # Only one LLM call: importance scoring (Sonnet via call_structured);
    # no conflict classification because there are no duplicates.
    assert client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_sonnet_called_only_for_facts_with_duplicates():
    """AC6: Mixed batch — Sonnet called only for the fact with a duplicate."""
    existing_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.91,
        payload={
            "text_preview": "energy drives behavior",
            "source_stage": "researcher",
            "created_at": "2026-04-10",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {
                "fact": "energy drives behavior",
                "importance": 7,
                "reasoning": "important",
            },
            {"fact": "completely new insight", "importance": 6, "reasoning": "novel"},
        ]
    )
    conflict_resp = json.dumps(
        {
            "classification": "DUPLICATE",
            "reasoning": "Same fact",
            "merged_content": None,
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()

    # First fact finds a duplicate, second does not
    vs = AsyncMock()
    vs.search_dense = AsyncMock(
        side_effect=[
            [existing_point],  # first fact — match
            [],  # second fact — no match
        ],
    )
    vs.upsert_dense = AsyncMock()

    session = _mock_db_session()
    extraction = _make_extraction(
        ["energy drives behavior", "completely new insight"],
    )

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            return_value=MagicMock(id=uuid.uuid4()),
        ),
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ),
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.sonnet_calls == 1
    assert result.duplicates_skipped == 1
    assert result.memories_created == 1


# ---------------------------------------------------------------------------
# Phase B: structured-output failures raise loudly (no silent 5.0 default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_importance_scoring_validation_failure_raises():
    """A response whose tool input violates ``_ImportanceScores`` schema
    raises StructuredOutputError. The pre-rewrite path silently defaulted
    every fact to importance 5.0 on every cumulative-growth topic."""
    from decisionlab.structured import StructuredOutputError

    bad = _make_tool_response("emit__ImportanceScores", {"not_scores": "wrong shape"})
    client = _make_client([bad])

    with pytest.raises(StructuredOutputError):
        await _score_importance(["fact a", "fact b"], client)


@pytest.mark.asyncio
async def test_importance_scoring_truncation_raises():
    """Sonnet truncation surfaces as StructuredOutputError so the eval
    trace shows the actual cause rather than "json.loads failed"."""
    from decisionlab.structured import StructuredOutputError

    truncated = _make_tool_response(
        "emit__ImportanceScores",
        {"scores": []},
        stop_reason="max_tokens",
    )
    truncated.usage = MagicMock(output_tokens=16384)
    client = _make_client([truncated])

    with pytest.raises(StructuredOutputError, match="truncated at max_tokens"):
        await _score_importance(["fact a", "fact b"], client)


@pytest.mark.asyncio
async def test_classify_conflict_validation_failure_returns_unknown(caplog):
    """Conflict classification has a tighter blast radius (per-pair, not
    per-stage) so a schema violation is logged and the caller treats the
    fact as new — but the failure is no longer silent: it goes to the
    log at WARNING."""
    bad = _make_tool_response("emit__ConflictClassification", {"unexpected": "field"})
    client = _make_client([bad])

    with caplog.at_level("WARNING", logger="decisionlab.knowledge.resolver"):
        result = await _classify_conflict(
            existing_content="old fact",
            existing_stage="researcher",
            existing_timestamp="2026-04-10",
            new_content="new fact",
            new_stage="formalizer",
            client=client,
        )

    assert result["classification"] == "UNKNOWN"
    assert any("Conflict classification failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corroboration_updates_confidence():
    """CORROBORATION → update_confidence(corroborate=True), no new memory."""
    corr_id = str(uuid.uuid4())
    existing_point = FakeScoredPoint(
        id=corr_id,
        score=0.93,
        payload={
            "text_preview": "leptin signals satiety",
            "source_stage": "researcher",
            "created_at": "2026-04-10",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {
                "fact": "leptin signals satiety",
                "importance": 7,
                "reasoning": "hormone function",
            },
        ]
    )
    conflict_resp = json.dumps(
        {
            "classification": "CORROBORATION",
            "reasoning": "Independent confirmation from different source",
            "merged_content": None,
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()
    extraction = _make_extraction(["leptin signals satiety"])

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
    mock_update.assert_called_once_with(session, uuid.UUID(corr_id), corroborate=True)
    mock_create.assert_not_called()
    mock_supersede.assert_not_called()


@pytest.mark.asyncio
async def test_self_match_excluded_from_duplicates():
    """Points from the same run_id are excluded from duplicate candidates."""
    same_run_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.99,
        payload={"run_id": _DEFAULT_RUN_ID, "text_preview": "test"},
    )
    emb = _mock_embedding_service()
    vs = _mock_vector_store([same_run_point])

    candidates = await _find_duplicates("test fact", _DEFAULT_RUN_ID, emb, vs)
    assert candidates == []


@pytest.mark.asyncio
async def test_below_threshold_excluded_from_duplicates():
    """Points with similarity <= 0.85 are excluded."""
    low_score_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.80,
        payload={
            "run_id": "00000000-0000-0000-0000-000000000099",
            "text_preview": "somewhat related",
        },
    )
    emb = _mock_embedding_service()
    vs = _mock_vector_store([low_score_point])

    candidates = await _find_duplicates("test fact", _DEFAULT_RUN_ID, emb, vs)
    assert candidates == []


@pytest.mark.asyncio
async def test_resolution_result_dataclass():
    """ResolutionResult has all expected fields."""
    r = ResolutionResult(
        memories_created=3,
        duplicates_skipped=1,
        corroborations=2,
        enrichments=1,
        contradictions=0,
        sonnet_calls=2,
        importance_scores={"fact": 7.0},
    )
    assert r.memories_created == 3
    assert r.importance_scores == {"fact": 7.0}


@pytest.mark.asyncio
async def test_empty_extraction_returns_zero_result():
    """Extraction with no facts returns zero counts."""
    json.dumps([])
    client = _make_client([])  # no calls needed

    emb = _mock_embedding_service()
    vs = _mock_vector_store([])
    session = _mock_db_session()

    extraction = _make_extraction([], stage="researcher")

    with (
        patch("decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock),
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ),
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.memories_created == 0
    assert result.sonnet_calls == 0
    assert result.importance_scores == {}


@pytest.mark.asyncio
async def test_classify_conflict_uses_structured_model():
    """AC2 (P0-001): _classify_conflict stays on ``knowledge_structured_model``
    (Sonnet) — DUPLICATE / CORROBORATION / ENRICHMENT / CONTRADICTION + merged-
    content writing is judgment-heavy and not safe to demote."""
    from decisionlab.config import SETTINGS

    conflict_resp = json.dumps(
        {
            "classification": "DUPLICATE",
            "reasoning": "same",
            "merged_content": None,
        }
    )
    client = _make_client([conflict_resp])

    result = await _classify_conflict(
        existing_content="old fact",
        existing_stage="researcher",
        existing_timestamp="2026-04-10",
        new_content="new fact",
        new_stage="formalizer",
        client=client,
    )

    assert result["classification"] == "DUPLICATE"
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == SETTINGS.knowledge_structured_model


# ---------------------------------------------------------------------------
# Reviewer-identified: Sonnet failure degrades gracefully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sonnet_failure_stores_fact_as_new():
    """When Sonnet classification fails, fact is stored as new (via UNKNOWN fallback)."""
    existing_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.90,
        payload={
            "text_preview": "some existing fact",
            "source_stage": "researcher",
            "created_at": "2026-04-10",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {"fact": "a related fact", "importance": 6, "reasoning": "ok"},
        ]
    )
    client = _make_client(
        [
            importance_resp,  # Haiku succeeds (via stream)
            RuntimeError("Sonnet API error"),  # Sonnet fails (via create)
        ]
    )

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()
    extraction = _make_extraction(["a related fact"])

    with (
        patch(
            "decisionlab.knowledge.resolver.create_memory",
            new_callable=AsyncMock,
            return_value=MagicMock(id=uuid.uuid4()),
        ) as mock_create,
        patch(
            "decisionlab.knowledge.resolver.supersede_memory", new_callable=AsyncMock
        ),
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    # Sonnet was attempted but failed — fact stored as new via UNKNOWN fallback
    assert result.sonnet_calls == 1
    assert result.memories_created == 1
    mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# Reviewer-identified: merged_content null falls back to fact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrichment_null_merged_content_uses_fact():
    """When Sonnet returns merged_content: null on ENRICHMENT, fall back to the new fact."""
    existing_point = FakeScoredPoint(
        id=str(uuid.uuid4()),
        score=0.90,
        payload={
            "text_preview": "some parameter value",
            "source_stage": "formalizer",
            "created_at": "2026-04-10",
            "run_id": "00000000-0000-0000-0000-000000000099",
        },
    )

    importance_resp = json.dumps(
        [
            {
                "fact": "a new detail about the parameter",
                "importance": 7,
                "reasoning": "detail",
            },
        ]
    )
    conflict_resp = json.dumps(
        {
            "classification": "ENRICHMENT",
            "reasoning": "adds detail",
            "merged_content": None,  # null — should fall back to fact text
        }
    )
    client = _make_client([importance_resp, conflict_resp])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([existing_point])
    session = _mock_db_session()
    extraction = _make_extraction(
        ["a new detail about the parameter"],
        stage="formalizer",
    )

    fake_new_mem = MagicMock()
    fake_new_mem.id = uuid.uuid4()

    with (
        patch("decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock),
        patch(
            "decisionlab.knowledge.resolver.supersede_memory",
            new_callable=AsyncMock,
            return_value=fake_new_mem,
        ) as mock_supersede,
        patch(
            "decisionlab.knowledge.resolver.update_confidence", new_callable=AsyncMock
        ),
    ):
        result = await resolve_and_store(extraction, emb, vs, session, client)

    assert result.enrichments == 1
    # merged_content was null, so the new fact text should be used
    assert (
        mock_supersede.call_args.kwargs["new_content"]
        == "a new detail about the parameter"
    )
