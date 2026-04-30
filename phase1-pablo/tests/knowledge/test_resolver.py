"""Tests for conflict resolution, importance scoring, and memory persistence.

Covers acceptance criteria AC1 through AC7 for issue P2-004.
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


def _make_response(text: str, *, stop_reason: str = "end_turn") -> MagicMock:
    """Build a mock Anthropic message response."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = stop_reason
    resp.usage = None
    return resp


class _StreamCM:
    """Async context manager mimicking ``client.messages.stream(...)``."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_final_message(self):
        return self._response


class _MessagesAPI:
    """Mimics ``client.messages``: both ``create`` and ``stream`` consume from
    the same response queue, so callers don't have to care which path the
    resolver picks. ``call_args`` and ``call_count`` are tracked per attr."""

    def __init__(self, queue: list):
        self._iter = iter(queue)
        self.create = AsyncMock(side_effect=self._next_response)
        self.stream = MagicMock(side_effect=self._next_stream_cm)

    def _next_response(self, **_kw):
        item = next(self._iter)
        if isinstance(item, BaseException) or (
            isinstance(item, type) and issubclass(item, BaseException)
        ):
            raise item
        return item

    def _next_stream_cm(self, **_kw):
        item = next(self._iter)
        if isinstance(item, BaseException) or (
            isinstance(item, type) and issubclass(item, BaseException)
        ):
            raise item
        return _StreamCM(item)


def _make_client(responses: list) -> MagicMock:
    """Wire both ``messages.create`` and ``messages.stream`` against a single
    response queue; whichever path the resolver picks next consumes the head."""
    queue = [r if not isinstance(r, str) else _make_response(r) for r in responses]
    client = MagicMock()
    client.messages = _MessagesAPI(queue)
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
async def test_importance_scoring_calls_haiku():
    """Importance scoring should call the Haiku model."""
    scored_response = json.dumps(
        [
            {"fact": "test fact", "importance": 5, "reasoning": "average"},
        ]
    )
    client = _make_client([scored_response])

    await _score_importance(["test fact"], client)

    # _score_importance now streams (max_tokens=16384), so check stream not create
    client.messages.stream.assert_called_once()
    call_kwargs = client.messages.stream.call_args.kwargs
    assert "haiku" in call_kwargs["model"]


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
    assert merged_text[:200] in upsert_kwargs.args[3]["text_preview"]


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
    # Only one LLM call — importance scoring (Haiku, now via stream); no Sonnet
    assert client.messages.stream.call_count == 1
    assert client.messages.create.call_count == 0


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
# AC7: Haiku failure defaults all facts to importance 5.0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_haiku_failure_defaults_importance_to_5():
    """AC7: If Haiku importance scoring fails, all facts default to 5.0 and processing continues."""
    # Haiku returns invalid JSON
    client = _make_client(["THIS IS NOT JSON"])

    emb = _mock_embedding_service()
    vs = _mock_vector_store([])
    session = _mock_db_session()

    extraction = _make_extraction(
        ["fact alpha", "fact beta"],
        stage="researcher",
    )

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

    assert result.memories_created == 2
    assert result.importance_scores == {"fact alpha": 5.0, "fact beta": 5.0}

    # Verify that create_memory was called with importance=5.0
    for c in mock_create.call_args_list:
        assert c.kwargs["importance"] == 5.0


@pytest.mark.asyncio
async def test_haiku_exception_defaults_importance_to_5():
    """AC7: If Haiku call raises exception, all facts default to 5.0."""
    # Both paths raise — covers create and stream entrypoints in case the
    # importance budget is later tuned across the streaming threshold.
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("API error"))
    client.messages.stream = MagicMock(side_effect=RuntimeError("API error"))

    scores = await _score_importance(["fact a", "fact b"], client)
    assert scores == {"fact a": 5.0, "fact b": 5.0}


@pytest.mark.asyncio
async def test_importance_scoring_truncation_logs_and_defaults_to_5(caplog):
    """When Haiku hits stop_reason='max_tokens', the underlying
    ``_call_llm_json`` raises and the broad except in ``_score_importance``
    defaults importance to 5.0 — but the log message must include the
    truncation reason rather than only ``Expecting value`` from json.loads."""
    truncated = _make_response('[{"fact": "fact a", "imp', stop_reason="max_tokens")
    truncated.usage = MagicMock(output_tokens=16384)
    client = _make_client([truncated])

    with caplog.at_level("WARNING", logger="decisionlab.knowledge.resolver"):
        scores = await _score_importance(["fact a", "fact b"], client)

    assert scores == {"fact a": 5.0, "fact b": 5.0}
    assert any("Importance scoring failed" in r.message for r in caplog.records)
    # Truncation has to surface in the traceback the warning attaches via
    # exc_info — otherwise the failure looks like a generic JSON error.
    truncation_logged = any(
        r.exc_info
        and r.exc_info[1] is not None
        and "truncated at max_tokens" in str(r.exc_info[1])
        for r in caplog.records
    )
    assert truncation_logged, "max_tokens truncation must be visible in the logs"


@pytest.mark.asyncio
async def test_classify_conflict_truncation_treats_as_unknown(caplog):
    """Same fail-loud-but-degrade-gracefully path for the Sonnet conflict
    classification call."""
    from decisionlab.knowledge.resolver import _classify_conflict

    truncated = _make_response('{"classification": "ENRIC', stop_reason="max_tokens")
    truncated.usage = MagicMock(output_tokens=4096)
    client = _make_client([truncated])

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
    truncation_logged = any(
        r.exc_info
        and r.exc_info[1] is not None
        and "truncated at max_tokens" in str(r.exc_info[1])
        for r in caplog.records
    )
    assert truncation_logged


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
async def test_classify_conflict_calls_sonnet():
    """_classify_conflict calls the Sonnet model."""
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
    assert "sonnet" in call_kwargs["model"]


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
