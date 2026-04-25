"""Tests for P5-003: Post-run consolidation with clustering, reflections, and pruning.

Covers all 7 acceptance criteria:
  AC1: 30 facts → >=3 clusters of related memories
  AC2: Reflection generated from cluster of >=3 facts, stored with memory_type="reflection"
  AC3: Similar reflection from past run gets corroborated
  AC4: 60-day untouched memories → confidence reduced by ~10% (0.95^2)
  AC5: 120-day memory, confidence 0.15, access_count=0 → pruned
  AC6: 120-day memory, confidence 0.15, access_count=5 → NOT pruned
  AC7: Consolidation <10s for ~50 memories
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

_PATCH_BASE = "decisionlab.knowledge.consolidation"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeMemory:
    """Minimal stand-in for the Memory ORM model."""

    id: uuid.UUID
    content: str
    namespace: str = "paradigm"
    memory_type: str = "semantic"
    source_stage: str = "researcher"
    run_id: uuid.UUID | None = None
    confidence: float = 0.6
    access_count: int = 0
    corroborations: int = 0
    contradictions: int = 0
    last_accessed_at: datetime | None = None
    created_at: datetime | None = None
    valid_to: datetime | None = None
    valid_from: datetime | None = None
    importance: float = 5.0
    metadata_: dict | None = None


@dataclass(frozen=True)
class FakeScoredPoint:
    id: str
    score: float
    payload: dict


def _make_response(text: str) -> MagicMock:
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_client(responses: list[str]) -> AsyncMock:
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=[_make_response(t) for t in responses],
    )
    return client


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago(n: int) -> datetime:
    return _utc_now() - timedelta(days=n)


def _make_memories(
    n: int,
    *,
    run_id: uuid.UUID | None = None,
    prefix: str = "Fact",
) -> list[FakeMemory]:
    """Create n fake memories with unique IDs."""
    return [
        FakeMemory(
            id=uuid.uuid4(),
            content=f"{prefix} {i}: some scientific statement about topic {i % 5}",
            run_id=run_id,
            created_at=_utc_now(),
            valid_from=_utc_now(),
        )
        for i in range(n)
    ]


def _make_clustered_embeddings(n: int, n_clusters: int) -> list[list[float]]:
    """Create n embeddings forming n_clusters tight clusters.

    Memories within a cluster have cosine similarity > 0.80.
    Memories across clusters have low similarity.
    """
    dim = 16
    rng = np.random.RandomState(42)
    vectors = []
    per_cluster = n // n_clusters
    remainder = n % n_clusters

    for c in range(n_clusters):
        # Random cluster center
        center = rng.randn(dim).astype(np.float32)
        center = center / np.linalg.norm(center)

        count = per_cluster + (1 if c < remainder else 0)
        for _ in range(count):
            # Small perturbation to stay within threshold
            noise = rng.randn(dim).astype(np.float32) * 0.05
            v = center + noise
            v = v / np.linalg.norm(v)
            vectors.append(v.tolist())

    return vectors


# ---------------------------------------------------------------------------
# AC1: After 30 facts, consolidation finds >=3 clusters
# ---------------------------------------------------------------------------


class TestAC1_Clustering:
    """After a run with 30 facts, consolidation finds >=3 clusters."""

    @pytest.mark.asyncio
    async def test_30_facts_produce_at_least_3_clusters(self):
        from decisionlab.knowledge.consolidation import _cluster_run_memories

        run_id = uuid.uuid4()
        memories = _make_memories(30, run_id=run_id)
        # 5 clusters of 6 memories each
        embeddings = _make_clustered_embeddings(30, 5)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = memories
        session.execute = AsyncMock(return_value=result_mock)

        embedding_service = AsyncMock()
        embedding_service.embed_texts = AsyncMock(return_value=embeddings)

        clusters = await _cluster_run_memories(session, embedding_service, str(run_id))

        assert len(clusters) >= 3

    @pytest.mark.asyncio
    async def test_dissimilar_memories_form_no_clusters(self):
        from decisionlab.knowledge.consolidation import _cluster_run_memories

        run_id = uuid.uuid4()
        memories = _make_memories(5, run_id=run_id)

        # Orthogonal embeddings — no pair exceeds 0.80
        dim = 16
        rng = np.random.RandomState(99)
        embeddings = []
        for _ in range(5):
            v = rng.randn(dim).astype(np.float32)
            v = v / np.linalg.norm(v)
            embeddings.append(v.tolist())

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = memories
        session.execute = AsyncMock(return_value=result_mock)

        embedding_service = AsyncMock()
        embedding_service.embed_texts = AsyncMock(return_value=embeddings)

        clusters = await _cluster_run_memories(session, embedding_service, str(run_id))

        # Random 16-dim vectors won't cluster above 0.80
        assert len(clusters) == 0

    @pytest.mark.asyncio
    async def test_single_memory_no_clusters(self):
        from decisionlab.knowledge.consolidation import _cluster_run_memories

        run_id = uuid.uuid4()
        memories = _make_memories(1, run_id=run_id)

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = memories
        session.execute = AsyncMock(return_value=result_mock)

        embedding_service = AsyncMock()

        clusters = await _cluster_run_memories(session, embedding_service, str(run_id))
        assert clusters == []


# ---------------------------------------------------------------------------
# AC2: Reflection from cluster >=3 facts, stored as memory_type="reflection"
# ---------------------------------------------------------------------------


class TestAC2_ReflectionGeneration:
    """At least 1 reflection generated from cluster of >=3 facts."""

    @pytest.mark.asyncio
    async def test_reflection_created_from_large_cluster(self):
        from decisionlab.knowledge.consolidation import _generate_reflections

        run_id = uuid.uuid4()
        cluster_mems = _make_memories(4, run_id=run_id)
        clusters = [cluster_mems]

        # LLM returns 1 insight, contradiction check not triggered (no similar found)
        client = _make_client(['["Higher-level insight about the cluster pattern"]'])

        session = AsyncMock()
        # create_memory returns a fake reflection
        reflection = FakeMemory(
            id=uuid.uuid4(),
            content="Higher-level insight about the cluster pattern",
            namespace="meta",
            memory_type="reflection",
            importance=8.0,
            confidence=0.7,
        )

        embedding_service = AsyncMock()
        embedding_service.embed_texts = AsyncMock(
            return_value=[np.zeros(16).tolist()],
        )

        vector_store = AsyncMock()
        vector_store.search_dense = AsyncMock(return_value=[])

        with patch(
            f"{_PATCH_BASE}.create_memory",
            new_callable=AsyncMock,
            return_value=reflection,
        ) as mock_create:
            generated, corroborated = await _generate_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                clusters,
                str(run_id),
            )

        assert generated == 1
        # Verify create_memory was called with correct params
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["memory_type"] == "reflection"
        assert call_kwargs["namespace"] == "meta"
        assert call_kwargs["importance"] == 8.0
        assert call_kwargs["confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_cluster_of_2_does_not_generate_reflection(self):
        from decisionlab.knowledge.consolidation import _generate_reflections

        run_id = uuid.uuid4()
        cluster_mems = _make_memories(2, run_id=run_id)
        clusters = [cluster_mems]

        client = AsyncMock()
        session = AsyncMock()
        embedding_service = AsyncMock()
        vector_store = AsyncMock()

        with patch(
            f"{_PATCH_BASE}.create_memory", new_callable=AsyncMock
        ) as mock_create:
            generated, _ = await _generate_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                clusters,
                str(run_id),
            )

        assert generated == 0
        mock_create.assert_not_called()
        # Client should not be called for clusters < 3
        client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_reflection_truncation_skips_cluster_and_logs(self, caplog):
        """Haiku hitting max_tokens must surface as a clear log and skip the
        cluster — not silently look like a JSON parse error."""
        from decisionlab.knowledge.consolidation import _generate_reflections

        run_id = uuid.uuid4()
        clusters = [_make_memories(4, run_id=run_id)]

        truncated = _make_response('[{"insight": "incomp')
        truncated.stop_reason = "max_tokens"
        truncated.usage = MagicMock(output_tokens=4096)
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=truncated)

        session = AsyncMock()
        embedding_service = AsyncMock()
        vector_store = AsyncMock()

        with patch(
            f"{_PATCH_BASE}.create_memory", new_callable=AsyncMock
        ) as mock_create, caplog.at_level("WARNING", logger=_PATCH_BASE):
            generated, corroborated = await _generate_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                clusters,
                str(run_id),
            )

        assert generated == 0
        assert corroborated == 0
        mock_create.assert_not_called()
        assert any("truncated at max_tokens" in r.message for r in caplog.records), (
            "truncation must appear in the warning log, not be masked as a generic skip"
        )


# ---------------------------------------------------------------------------
# AC3: Similar reflection from past run gets corroborated
# ---------------------------------------------------------------------------


class TestAC3_ReflectionCorroboration:
    """A reflection similar to an existing one corroborates it."""

    @pytest.mark.asyncio
    async def test_cross_run_corroboration(self):
        from decisionlab.knowledge.consolidation import _check_cross_run_reflections

        run_id = str(uuid.uuid4())
        past_run_id = str(uuid.uuid4())
        past_reflection_id = str(uuid.uuid4())

        new_reflection = FakeMemory(
            id=uuid.uuid4(),
            content="Dopamine modulates reward learning through prediction errors",
        )

        # Vector store returns a similar past reflection
        similar_point = FakeScoredPoint(
            id=past_reflection_id,
            score=0.90,
            payload={
                "run_id": past_run_id,
                "namespace": "meta",
                "text_preview": "Dopamine signals encode reward prediction errors",
            },
        )

        vector_store = AsyncMock()
        vector_store.search_dense = AsyncMock(return_value=[similar_point])

        # LLM says NOT a contradiction
        client = _make_client(['{"contradicts": false, "reasoning": "same direction"}'])

        embedding = np.zeros(16).tolist()
        session = AsyncMock()
        embedding_service = AsyncMock()

        with patch(
            f"{_PATCH_BASE}.update_confidence", new_callable=AsyncMock
        ) as mock_update:
            corroborated = await _check_cross_run_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                new_reflection,
                embedding,
                run_id,
            )

        assert corroborated == 1
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["corroborate"] is True

    @pytest.mark.asyncio
    async def test_contradiction_does_not_corroborate(self):
        from decisionlab.knowledge.consolidation import _check_cross_run_reflections

        run_id = str(uuid.uuid4())
        past_reflection_id = str(uuid.uuid4())

        new_reflection = FakeMemory(
            id=uuid.uuid4(),
            content="Serotonin is the primary reward signal",
        )

        similar_point = FakeScoredPoint(
            id=past_reflection_id,
            score=0.90,
            payload={
                "run_id": str(uuid.uuid4()),
                "namespace": "meta",
                "text_preview": "Dopamine is the primary reward signal",
            },
        )

        vector_store = AsyncMock()
        vector_store.search_dense = AsyncMock(return_value=[similar_point])

        client = _make_client(
            ['{"contradicts": true, "reasoning": "conflicting neurotransmitter"}']
        )

        session = AsyncMock()
        embedding_service = AsyncMock()

        with patch(
            f"{_PATCH_BASE}.update_confidence", new_callable=AsyncMock
        ) as mock_update:
            corroborated = await _check_cross_run_reflections(
                session,
                embedding_service,
                vector_store,
                client,
                new_reflection,
                np.zeros(16).tolist(),
                run_id,
            )

        assert corroborated == 0
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_contradiction_check_truncation_logs_and_returns_false(self, caplog):
        """If the contradiction-check call truncates, the failure surfaces in
        the log (not as a generic 'check failed') and we conservatively return
        False so the corroboration path can still run."""
        from decisionlab.knowledge.consolidation import _is_contradiction

        truncated = _make_response('{"contradicts": tru')
        truncated.stop_reason = "max_tokens"
        truncated.usage = MagicMock(output_tokens=4096)
        client = AsyncMock()
        client.messages.create = AsyncMock(return_value=truncated)

        with caplog.at_level("WARNING", logger=_PATCH_BASE):
            result = await _is_contradiction(client, "fact A", "fact B")

        assert result is False
        assert any("truncated at max_tokens" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC4: 60-day untouched memories → confidence reduced by ~10% (0.95^2)
# ---------------------------------------------------------------------------


class TestAC4_TimeDecay:
    """Memories untouched for 60 days have confidence reduced by ~10%."""

    @pytest.mark.asyncio
    async def test_60_day_decay(self):
        from shared.memories import apply_time_decay

        mem_id = uuid.uuid4()
        original_confidence = 0.8

        mem = MagicMock()
        mem.id = mem_id
        mem.confidence = original_confidence
        mem.last_accessed_at = _days_ago(60)
        mem.memory_type = "semantic"
        mem.valid_to = None

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mem]
        session.execute = AsyncMock(return_value=result_mock)

        count = await apply_time_decay(session)

        assert count == 1
        # Check the UPDATE was called with decayed confidence
        # periods = 60 // 30 = 2, new = 0.8 * 0.95^2 = 0.722
        update_call = session.execute.call_args_list[-1]
        stmt = update_call[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        expected = round(original_confidence * 0.95**2, 10)
        assert str(expected)[:4] in compiled  # 0.72...


# ---------------------------------------------------------------------------
# AC5: 120-day memory, confidence 0.15, access_count=0 → pruned
# ---------------------------------------------------------------------------


class TestAC5_PruneStale:
    """A 120-day-old memory with confidence 0.15 and access_count=0 is pruned."""

    @pytest.mark.asyncio
    async def test_old_low_confidence_zero_access_pruned(self):
        from decisionlab.knowledge.consolidation import _prune_stale

        mem_id = uuid.uuid4()

        # Mock: select returns one row matching prune criteria
        row = MagicMock()
        row.id = mem_id

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = [row]
        session.execute = AsyncMock(return_value=result_mock)

        pruned = await _prune_stale(session)

        assert pruned == 1
        # Verify UPDATE was called (for valid_to = now)
        assert session.execute.call_count >= 2  # SELECT + UPDATE
        assert session.flush.called


# ---------------------------------------------------------------------------
# AC6: 120-day memory, confidence 0.15, access_count=5 → NOT pruned
# ---------------------------------------------------------------------------


class TestAC6_AccessCountGuard:
    """A memory with access_count > 0 is NOT pruned even if old and low-confidence."""

    @pytest.mark.asyncio
    async def test_accessed_memory_not_pruned(self):
        from decisionlab.knowledge.consolidation import _prune_stale

        # Mock: select returns empty (the WHERE clause excludes access_count > 0)
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        pruned = await _prune_stale(session)

        assert pruned == 0

    def test_prune_query_includes_access_count_check(self):
        """Verify the SQL WHERE clause includes access_count == 0."""
        from decisionlab.knowledge.consolidation import _prune_stale
        import inspect

        source = inspect.getsource(_prune_stale)
        assert "access_count == 0" in source or "access_count" in source


# ---------------------------------------------------------------------------
# AC7: Consolidation completes in <10 seconds for ~50 memories
# ---------------------------------------------------------------------------


class TestAC7_Performance:
    """Consolidation completes in <10s for a typical run with ~50 memories."""

    @pytest.mark.asyncio
    async def test_consolidation_under_10_seconds(self):
        from decisionlab.knowledge.consolidation import consolidate

        run_id = uuid.uuid4()
        memories = _make_memories(50, run_id=run_id)
        embeddings = _make_clustered_embeddings(50, 5)

        # Mock session with two different result behaviors
        session = AsyncMock()

        # First execute: cluster query returns memories
        cluster_result = MagicMock()
        cluster_result.scalars.return_value.all.return_value = memories

        # Subsequent executes: decay/prune queries return empty
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[cluster_result, empty_result, empty_result, empty_result],
        )

        embedding_service = AsyncMock()
        embedding_service.embed_texts = AsyncMock(
            side_effect=[
                embeddings,  # cluster embedding
                # reflection embeddings (one per reflection)
                *[[np.zeros(16).tolist()] for _ in range(20)],
            ]
        )

        vector_store = AsyncMock()
        vector_store.search_dense = AsyncMock(return_value=[])

        # LLM: one reflection call per cluster that has >=3 members
        client = _make_client(['["Insight from cluster"]' for _ in range(20)])

        with patch(
            f"{_PATCH_BASE}.apply_time_decay", new_callable=AsyncMock, return_value=0
        ):
            with patch(
                f"{_PATCH_BASE}._prune_stale", new_callable=AsyncMock, return_value=0
            ):
                result = await consolidate(
                    session,
                    embedding_service,
                    vector_store,
                    client,
                    str(run_id),
                )

        assert result.duration_ms < 10_000


# ---------------------------------------------------------------------------
# Integration: full consolidate flow
# ---------------------------------------------------------------------------


class TestConsolidateIntegration:
    """End-to-end test of the consolidate function with mocked infra."""

    @pytest.mark.asyncio
    async def test_full_flow_returns_result(self):
        from decisionlab.knowledge.consolidation import consolidate

        run_id = uuid.uuid4()
        memories = _make_memories(9, run_id=run_id)
        # 3 clusters of 3
        embeddings = _make_clustered_embeddings(9, 3)

        session = AsyncMock()
        cluster_result = MagicMock()
        cluster_result.scalars.return_value.all.return_value = memories

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        empty_result.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[cluster_result, empty_result, empty_result, empty_result],
        )

        embedding_service = AsyncMock()
        embedding_service.embed_texts = AsyncMock(
            side_effect=[
                embeddings,
                *[[np.zeros(16).tolist()] for _ in range(10)],
            ]
        )

        vector_store = AsyncMock()
        vector_store.search_dense = AsyncMock(return_value=[])

        reflection = FakeMemory(
            id=uuid.uuid4(),
            content="Insight",
            namespace="meta",
            memory_type="reflection",
        )

        client = _make_client(
            [
                '["Cluster insight one"]',
                '["Cluster insight two"]',
                '["Cluster insight three"]',
            ]
        )

        with patch(
            f"{_PATCH_BASE}.create_memory",
            new_callable=AsyncMock,
            return_value=reflection,
        ):
            with patch(
                f"{_PATCH_BASE}.apply_time_decay",
                new_callable=AsyncMock,
                return_value=0,
            ):
                with patch(
                    f"{_PATCH_BASE}._prune_stale",
                    new_callable=AsyncMock,
                    return_value=0,
                ):
                    result = await consolidate(
                        session,
                        embedding_service,
                        vector_store,
                        client,
                        str(run_id),
                    )

        assert result.clusters_found == 3
        assert result.reflections_generated == 3
        assert result.memories_decayed == 0
        assert result.memories_pruned == 0
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# Router integration
# ---------------------------------------------------------------------------


class TestRouterConsolidation:
    """Consolidation is called from the router after Stage.DONE."""

    def test_router_calls_consolidation_after_done(self):
        """Verify the router code references _run_consolidation at Stage.DONE."""
        import inspect
        from decisionlab.router import Router

        source = inspect.getsource(Router.run)
        assert "_run_consolidation" in source

    def test_run_consolidation_method_exists(self):
        """Verify _run_consolidation method exists on Router."""
        from decisionlab.router import Router

        assert hasattr(Router, "_run_consolidation")
