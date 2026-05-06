"""Tests for P5-002: Confidence evolution with corroboration, contradiction, and decay.

Covers all 6 acceptance criteria:
  AC1: Corroboration boosts confidence (+0.05 per independent run)
  AC2: Contradiction decreases confidence (-0.10)
  AC3: Access boost (+0.02 per retrieval, capped at 1.0)
  AC4: Time decay (~14% reduction for 90-day untouched memory)
  AC5: High-confidence memories rank above low-confidence in retrieval
  AC6: Confidence never drops below 0.1
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.tool import _apply_recency_weighting

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_iso(days_ago: int = 0) -> str:
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _result(text: str, score: float, source: str, **meta) -> RetrievalResult:
    return RetrievalResult(text=text, score=score, source=source, metadata=dict(meta))


# ---------------------------------------------------------------------------
# AC1: Corroboration boosts — 3 independent runs → confidence = initial + 3*0.05
# ---------------------------------------------------------------------------


class TestAC1_CorroborationBoost:
    """A memory corroborated 3 times has confidence = initial + 3*0.05."""

    @pytest.mark.asyncio
    async def test_single_corroboration_adds_005(self):
        """One corroboration adds exactly +0.05 to confidence."""
        from shared.memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await update_confidence(session, mem_id, corroborate=True)

        session.execute.assert_called_once()
        stmt = session.execute.call_args[0][0]
        # Verify the compiled SQL contains the +0.05 delta
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "0.05" in compiled

    @pytest.mark.asyncio
    async def test_corroboration_capped_at_1(self):
        """Confidence cannot exceed 1.0 after corroboration."""
        from shared.memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await update_confidence(session, mem_id, corroborate=True)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Should use least/greatest clamping
        assert "least" in compiled.lower() or "LEAST" in compiled


# ---------------------------------------------------------------------------
# AC2: Contradiction decreases confidence by -0.10
# ---------------------------------------------------------------------------


class TestAC2_ContradictionPenalty:
    """A contradicted memory has confidence decreased by 0.10."""

    @pytest.mark.asyncio
    async def test_contradiction_subtracts_010(self):
        """Contradiction applies -0.10 delta."""
        from shared.memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await update_confidence(session, mem_id, contradict=True)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "0.1" in compiled  # -0.10 delta

    @pytest.mark.asyncio
    async def test_contradiction_logs_episodic_memory(self):
        """CONTRADICTION creates an episodic memory logging the event."""
        from decisionlab.knowledge.models import ExtractionResult
        from decisionlab.knowledge.resolver import resolve_and_store

        old_id = str(uuid.uuid4())
        existing_point = MagicMock()
        existing_point.id = old_id
        existing_point.score = 0.88
        existing_point.payload = {
            "text_preview": "setpoint = 50",
            "source_stage": "reasoner",
            "created_at": "2026-04-10T00:00:00Z",
            "run_id": "00000000-0000-0000-0000-000000000099",
        }

        # Both importance scoring and conflict classification now route
        # through call_structured (forced tool-use) — see Phase B of
        # research-memory-rewrite.md.
        def _tool_resp(tool_name, payload):
            block = MagicMock()
            block.type = "tool_use"
            block.name = tool_name
            block.input = payload
            resp = MagicMock()
            resp.content = [block]
            resp.stop_reason = "end_turn"
            resp.usage = None
            return resp

        importance_resp = _tool_resp(
            "emit__ImportanceScores",
            {
                "scores": [
                    {
                        "fact": "setpoint = 70",
                        "importance": 8,
                        "reasoning": "update",
                    }
                ]
            },
        )
        conflict_resp = _tool_resp(
            "emit__ConflictClassification",
            {
                "classification": "CONTRADICTION",
                "reasoning": "Different values",
                "merged_content": None,
            },
        )

        responses = iter([importance_resp, conflict_resp])

        async def _create(**_kw):
            return next(responses)

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(side_effect=_create)

        emb = AsyncMock()
        emb.embed_query = AsyncMock(return_value=[0.1] * 1024)

        vs = AsyncMock()
        vs.search_dense = AsyncMock(return_value=[existing_point])
        vs.upsert_dense = AsyncMock()

        session = AsyncMock()

        extraction = ExtractionResult(
            nodes=[],
            relations=[],
            facts=["setpoint = 70"],
            stage="reasoner",
            run_id="00000000-0000-0000-0000-000000000001",
        )

        fake_new_mem = MagicMock()
        fake_new_mem.id = uuid.uuid4()

        with (
            patch(
                "decisionlab.knowledge.resolver.create_memory", new_callable=AsyncMock
            ) as mock_create,
            patch(
                "decisionlab.knowledge.resolver.supersede_memory",
                new_callable=AsyncMock,
                return_value=fake_new_mem,
            ),
            patch(
                "decisionlab.knowledge.resolver.update_confidence",
                new_callable=AsyncMock,
            ),
        ):
            await resolve_and_store(extraction, emb, vs, session, client)

        # An episodic memory should have been created for the contradiction event
        assert mock_create.call_count >= 1
        episodic_calls = [
            c
            for c in mock_create.call_args_list
            if c.kwargs.get("memory_type") == "episodic"
        ]
        assert len(episodic_calls) == 1
        episodic_content = episodic_calls[0].kwargs["content"]
        assert "contradicted" in episodic_content.lower()
        assert "setpoint = 50" in episodic_content
        assert "setpoint = 70" in episodic_content


# ---------------------------------------------------------------------------
# AC3: Access boost — 10 accesses → +0.20, capped at 1.0
# ---------------------------------------------------------------------------


class TestAC3_AccessBoost:
    """Each retrieval access boosts confidence by +0.02, capped at 1.0."""

    @pytest.mark.asyncio
    async def test_touch_memory_boosts_confidence(self):
        """touch_memory adds +0.02 to confidence."""
        from shared.memories import touch_memory

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await touch_memory(session, mem_id)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "0.02" in compiled

    @pytest.mark.asyncio
    async def test_touch_memory_capped_at_1(self):
        """Confidence from access boost is capped at 1.0."""
        from shared.memories import touch_memory

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await touch_memory(session, mem_id)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "least" in compiled.lower() or "LEAST" in compiled


# ---------------------------------------------------------------------------
# AC4: Time decay — 90-day untouched memory confidence reduced by ~14% (0.95^3)
# ---------------------------------------------------------------------------


class TestAC4_TimeDecay:
    """Time decay: confidence *= 0.95 per 30-day period of no access."""

    @pytest.mark.asyncio
    async def test_apply_time_decay_reduces_old_memories(self):
        """90-day untouched memory: confidence *= 0.95^3 ≈ 0.857."""
        from shared.memories import apply_time_decay

        session = AsyncMock()

        mem = MagicMock()
        mem.id = uuid.uuid4()
        mem.confidence = 1.0
        mem.memory_type = "semantic"
        mem.last_accessed_at = datetime.now(UTC) - timedelta(days=90)
        mem.valid_to = None

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem]
        session.execute = AsyncMock(return_value=result_mock)

        count = await apply_time_decay(session)

        assert count == 1
        # The update call is the second execute (first is the select)
        update_call = session.execute.call_args_list[1]
        stmt = update_call[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # 0.95^3 ≈ 0.857375
        expected = 0.95**3
        assert str(round(expected, 6)) in compiled or f"{expected}" in compiled

    @pytest.mark.asyncio
    async def test_reflections_exempt_from_decay(self):
        """Memories with memory_type='reflection' are not decayed."""
        from shared.memories import apply_time_decay

        session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        await apply_time_decay(session)

        # The query should filter out reflections
        stmt = session.execute.call_args_list[0][0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "reflection" in compiled.lower()

    @pytest.mark.asyncio
    async def test_decay_floors_at_01(self):
        """0.15 * 0.95^12 ≈ 0.082 → floored to 0.1."""
        from shared.memories import apply_time_decay

        session = AsyncMock()

        mem = MagicMock()
        mem.id = uuid.uuid4()
        mem.confidence = 0.15
        mem.memory_type = "semantic"
        mem.last_accessed_at = datetime.now(UTC) - timedelta(days=365)
        mem.valid_to = None

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem]
        session.execute = AsyncMock(return_value=result_mock)

        await apply_time_decay(session)

        # The update call writes floored confidence
        update_call = session.execute.call_args_list[1]
        stmt = update_call[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # 0.15 * 0.95^12 ≈ 0.082 → floored to 0.1
        assert "0.1" in compiled

    @pytest.mark.asyncio
    async def test_null_last_accessed_at_skipped(self):
        """Memories with NULL last_accessed_at are safely skipped."""
        from shared.memories import apply_time_decay

        session = AsyncMock()

        mem = MagicMock()
        mem.id = uuid.uuid4()
        mem.confidence = 0.8
        mem.memory_type = "semantic"
        mem.last_accessed_at = None
        mem.valid_to = None

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem]
        session.execute = AsyncMock(return_value=result_mock)

        count = await apply_time_decay(session)

        assert count == 0
        # Only the select call, no update
        assert session.execute.call_count == 1


# ---------------------------------------------------------------------------
# AC5: High-confidence memories rank above low-confidence in retrieval
# ---------------------------------------------------------------------------


class TestAC5_ConfidenceInRetrieval:
    """Retrieval scoring includes confidence as a multiplicative factor."""

    def test_high_confidence_ranks_above_low(self):
        """Same base score + recency: high confidence wins."""
        ts = _utc_iso(0)
        results = [
            _result("Low conf", 0.9, "dense", created_at=ts, confidence=0.3),
            _result("High conf", 0.9, "dense", created_at=ts, confidence=0.9),
        ]

        weighted = _apply_recency_weighting(results)

        assert weighted[0].text == "High conf"
        assert weighted[0].score > weighted[1].score

    def test_confidence_factor_in_score_calculation(self):
        """Final score = base_score * recency_factor * confidence."""
        ts = _utc_iso(30)
        results = [_result("Test", 1.0, "dense", created_at=ts, confidence=0.5)]

        weighted = _apply_recency_weighting(results)

        recency = 0.995**30
        expected = 1.0 * recency * 0.5
        assert weighted[0].score == pytest.approx(expected, rel=1e-3)

    def test_missing_confidence_defaults_to_1(self):
        """Results without confidence metadata get factor 1.0 (no penalty)."""
        ts = _utc_iso(0)
        results = [_result("No conf", 0.8, "web", created_at=ts)]

        weighted = _apply_recency_weighting(results)

        # Without confidence key, factor is 1.0 → score stays ~0.8
        assert weighted[0].score == pytest.approx(0.8, rel=0.01)

    def test_confidence_factor_stored_in_metadata(self):
        """The confidence_factor is included in result metadata."""
        ts = _utc_iso(0)
        results = [_result("Test", 0.9, "dense", created_at=ts, confidence=0.7)]

        weighted = _apply_recency_weighting(results)

        assert "confidence_factor" in weighted[0].metadata
        assert weighted[0].metadata["confidence_factor"] == pytest.approx(0.7)

    def test_out_of_range_confidence_clamped(self):
        """Confidence values > 1.0 or < 0.0 in payload are clamped."""
        ts = _utc_iso(0)
        results = [
            _result("Over", 0.9, "dense", created_at=ts, confidence=1.5),
            _result("Under", 0.9, "dense", created_at=ts, confidence=-0.5),
        ]

        weighted = _apply_recency_weighting(results)

        for r in weighted:
            assert 0.0 <= r.metadata["confidence_factor"] <= 1.0


# ---------------------------------------------------------------------------
# AC6: Confidence never drops below 0.1
# ---------------------------------------------------------------------------


class TestAC6_ConfidenceFloor:
    """Confidence is floored at 0.1 in all operations."""

    @pytest.mark.asyncio
    async def test_contradiction_floors_at_01(self):
        """Multiple contradictions cannot drop confidence below 0.1."""
        from shared.memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await update_confidence(session, mem_id, contradict=True)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Must have a floor of 0.1
        assert "greatest" in compiled.lower() or "GREATEST" in compiled
        assert "0.1" in compiled

    @pytest.mark.asyncio
    async def test_corroboration_and_contradiction_both_clamped(self):
        """Both operations simultaneously are clamped."""
        from shared.memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        await update_confidence(session, mem_id, corroborate=True, contradict=True)

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Net delta is 0.05 - 0.10 = -0.05
        assert "greatest" in compiled.lower() or "GREATEST" in compiled
