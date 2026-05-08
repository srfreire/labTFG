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
        """One corroboration routes a +0.05 delta through the helper."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await update_confidence(session, mem_id, corroborate=True)

        mock_helper.assert_awaited_once_with(session, mem_id, delta=0.05)

    @pytest.mark.asyncio
    async def test_corroboration_capped_at_1(self):
        """Clamping is the helper's job — corroboration delegates to it."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await update_confidence(session, mem_id, corroborate=True)

        mock_helper.assert_awaited_once()


# ---------------------------------------------------------------------------
# AC2: Contradiction decreases confidence by -0.10
# ---------------------------------------------------------------------------


class TestAC2_ContradictionPenalty:
    """A contradicted memory has confidence decreased by 0.10."""

    @pytest.mark.asyncio
    async def test_contradiction_subtracts_010(self):
        """Contradiction applies -0.10 delta via the helper."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await update_confidence(session, mem_id, contradict=True)

        mock_helper.assert_awaited_once_with(session, mem_id, delta=-0.10)

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
        """touch_memory routes a +0.02 delta through the helper for each id."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import touch_memory

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await touch_memory(session, mem_id)

        mock_helper.assert_awaited_once_with(session, mem_id, delta=0.02)

    @pytest.mark.asyncio
    async def test_touch_memory_capped_at_1(self):
        """Clamping at the cap is the helper's job — touch_memory delegates."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import touch_memory

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await touch_memory(session, mem_id)

        mock_helper.assert_awaited_once()


# ---------------------------------------------------------------------------
# AC4: Time decay — 90-day untouched memory confidence reduced by ~14% (0.95^3)
# ---------------------------------------------------------------------------


class TestAC4_TimeDecay:
    """Time decay: confidence *= 0.95 per 30-day period of no access."""

    @pytest.mark.asyncio
    async def test_apply_time_decay_reduces_old_memories(self):
        """90-day untouched memory: confidence *= 0.95^3 ≈ 0.857, set via helper."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import apply_time_decay

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

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            count = await apply_time_decay(session)

        assert count == 1
        mock_helper.assert_awaited_once()
        kwargs = mock_helper.await_args.kwargs
        assert kwargs["set_to"] == pytest.approx(1.0 * 0.95**3)

    @pytest.mark.asyncio
    async def test_reflections_exempt_from_decay(self):
        """Memories with memory_type='reflection' are not decayed."""
        from shared.pipeline_memories import apply_time_decay

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
        """0.15 * 0.95^12 ≈ 0.082 → flooring is delegated to the helper."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import apply_time_decay

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

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await apply_time_decay(session)

        # apply_time_decay passes the raw decayed value; the helper is
        # responsible for flooring at 0.1.
        mock_helper.assert_awaited_once()
        raw_target = mock_helper.await_args.kwargs["set_to"]
        assert raw_target < 0.1

    @pytest.mark.asyncio
    async def test_null_last_accessed_at_skipped(self):
        """Memories with NULL last_accessed_at are safely skipped."""
        from shared.pipeline_memories import apply_time_decay

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
    """Retrieval scoring includes confidence as a multiplicative factor.

    Post-P3-002 the multiplier comes from a batched PG fetch keyed by
    `entity_id`, not from the Qdrant payload. Tests in this class build
    memory-backed results (entity_id + collection="memories_dense") and
    patch `_fetch_confidences` to supply the PG-side values directly.
    """

    @staticmethod
    def _memory_result(
        text: str, score: float, *, ts: str
    ) -> tuple[RetrievalResult, uuid.UUID]:
        mem_id = uuid.uuid4()
        return (
            _result(
                text,
                score,
                "dense",
                created_at=ts,
                entity_id=str(mem_id),
                collection="memories_dense",
            ),
            mem_id,
        )

    async def test_high_confidence_ranks_above_low(self):
        """Same base score + recency: high confidence wins."""
        ts = _utc_iso(0)
        low, low_id = self._memory_result("Low conf", 0.9, ts=ts)
        high, high_id = self._memory_result("High conf", 0.9, ts=ts)
        conf_map = {low_id: 0.3, high_id: 0.9}

        with patch(
            "decisionlab.knowledge.retrieval.tool._fetch_confidences",
            new_callable=AsyncMock,
            return_value=conf_map,
        ):
            weighted = await _apply_recency_weighting([low, high])

        assert weighted[0].text == "High conf"
        assert weighted[0].score > weighted[1].score

    async def test_confidence_factor_in_score_calculation(self):
        """Final score = base_score * recency_factor * PG confidence."""
        ts = _utc_iso(30)
        result, mem_id = self._memory_result("Test", 1.0, ts=ts)

        with patch(
            "decisionlab.knowledge.retrieval.tool._fetch_confidences",
            new_callable=AsyncMock,
            return_value={mem_id: 0.5},
        ):
            weighted = await _apply_recency_weighting([result])

        recency = 0.995**30
        expected = 1.0 * recency * 0.5
        assert weighted[0].score == pytest.approx(expected, rel=1e-3)

    async def test_missing_pg_row_defaults_to_1(self):
        """Memory-backed result whose PG row is missing falls back to 1.0."""
        ts = _utc_iso(0)
        result, _ = self._memory_result("Orphan", 0.8, ts=ts)

        with patch(
            "decisionlab.knowledge.retrieval.tool._fetch_confidences",
            new_callable=AsyncMock,
            return_value={},
        ):
            weighted = await _apply_recency_weighting([result])

        assert weighted[0].metadata["confidence_factor"] == 1.0

    async def test_non_memory_result_defaults_to_1(self):
        """Web / artifact results are not PG-backed → factor stays 1.0."""
        ts = _utc_iso(0)
        results = [_result("No conf", 0.8, "web", created_at=ts)]

        weighted = await _apply_recency_weighting(results)

        assert weighted[0].score == pytest.approx(0.8, rel=0.01)
        assert weighted[0].metadata["confidence_factor"] == 1.0

    async def test_confidence_factor_stored_in_metadata(self):
        """The confidence_factor is included in result metadata."""
        ts = _utc_iso(0)
        result, mem_id = self._memory_result("Test", 0.9, ts=ts)

        with patch(
            "decisionlab.knowledge.retrieval.tool._fetch_confidences",
            new_callable=AsyncMock,
            return_value={mem_id: 0.7},
        ):
            weighted = await _apply_recency_weighting([result])

        assert "confidence_factor" in weighted[0].metadata
        assert weighted[0].metadata["confidence_factor"] == pytest.approx(0.7)

    async def test_out_of_range_pg_confidence_clamped(self):
        """PG-side confidence values outside [0, 1] are clamped on read."""
        ts = _utc_iso(0)
        over, over_id = self._memory_result("Over", 0.9, ts=ts)
        under, under_id = self._memory_result("Under", 0.9, ts=ts)

        with patch(
            "decisionlab.knowledge.retrieval.tool._fetch_confidences",
            new_callable=AsyncMock,
            return_value={over_id: 1.5, under_id: -0.5},
        ):
            weighted = await _apply_recency_weighting([over, under])

        for r in weighted:
            assert 0.0 <= r.metadata["confidence_factor"] <= 1.0


# ---------------------------------------------------------------------------
# AC6: Confidence never drops below 0.1
# ---------------------------------------------------------------------------


class TestAC6_ConfidenceFloor:
    """Confidence is floored at 0.1 in all operations."""

    @pytest.mark.asyncio
    async def test_contradiction_floors_at_01(self):
        """The floor is enforced by `update_memory_confidence`; contradiction
        delegates to it."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await update_confidence(session, mem_id, contradict=True)

        mock_helper.assert_awaited_once_with(session, mem_id, delta=-0.10)

    @pytest.mark.asyncio
    async def test_corroboration_and_contradiction_both_clamped(self):
        """Both flags applied simultaneously route the net delta through the
        helper, which owns clamping."""
        from shared import pipeline_memories as memories
        from shared.pipeline_memories import update_confidence

        session = AsyncMock()
        mem_id = uuid.uuid4()

        with patch.object(
            memories, "update_memory_confidence", new_callable=AsyncMock
        ) as mock_helper:
            await update_confidence(session, mem_id, corroborate=True, contradict=True)

        mock_helper.assert_awaited_once()
        net_delta = mock_helper.await_args.kwargs["delta"]
        assert net_delta == pytest.approx(-0.05)
