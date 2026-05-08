"""Tests for the embedding & Qdrant indexing pipeline (P2-003)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from decisionlab.knowledge.indexer import chunk_stage_output, index_stage_output
from decisionlab.knowledge.models import ExtractionResult, IndexResult

# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------


class TestChunkStageOutput:
    """Tests for stage-specific chunking logic."""

    def test_researcher_splits_by_section_headers(self):
        """AC1: A deep report is chunked into sections by ## headers."""
        text = (
            "# Homeostatic Regulation\n\n"
            "## Foundations\nSome foundational text about homeostasis.\n\n"
            "## Postulates\nP1: Energy balance is maintained.\n"
            "P2: Ghrelin modulates hunger.\n\n"
            "## Assumptions\nWe assume normal physiology.\n\n"
            "## Predictions\nGhrelin levels predict hunger.\n\n"
            "## Variables\nEnergy, hunger, ghrelin, leptin.\n\n"
            "## References\nDoe 2020. Smith 2021.\n"
        )
        chunks = chunk_stage_output("researcher", text)
        artifact_chunks = [c for c in chunks if c.chunk_type == "artifact"]
        assert len(artifact_chunks) >= 5
        assert all(c.chunk_type == "artifact" for c in artifact_chunks)
        # Each section should have a source_section set
        sections = [c.source_section for c in artifact_chunks]
        assert "Foundations" in sections
        assert "Postulates" in sections

    def test_formalizer_splits_by_formulation(self):
        text = (
            "# Formulations\n\n"
            "### Formulation 1: Drive-Reduction RL\n"
            "Some math here with LaTeX.\n\n"
            "### Formulation 2: Incentive Salience\n"
            "More math about incentive salience.\n\n"
            "### Formulation 3: Optimal Foraging\n"
            "Optimal foraging theory.\n"
        )
        chunks = chunk_stage_output("formalizer", text)
        assert len(chunks) == 3
        assert all(c.chunk_type == "artifact" for c in chunks)
        assert chunks[0].source_section == "Formulation 1: Drive-Reduction RL"

    def test_reasoner_single_chunk_for_small_json(self):
        text = '{"parameters": {"lr": 0.1}, "env_mapping": {"x": "position"}}'
        chunks = chunk_stage_output("reasoner", text)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "artifact"
        assert chunks[0].source_section is None

    def test_reasoner_splits_large_json(self):
        big = {f"key_{i}": "x" * 500 for i in range(10)}
        text = json.dumps(big)
        assert len(text) > 4000
        chunks = chunk_stage_output("reasoner", text)
        assert len(chunks) > 1
        assert all(c.chunk_type == "artifact" for c in chunks)

    def test_builder_creates_code_and_test_chunks(self):
        text = (
            "```python\n# model.py\nclass MyModel:\n    pass\n```\n\n"
            "```python\n# test_model.py\ndef test_it():\n    pass\n```\n"
        )
        chunks = chunk_stage_output("builder", text)
        assert len(chunks) == 2
        assert all(c.chunk_type == "artifact" for c in chunks)

    def test_builder_single_block_creates_one_chunk(self):
        text = "class MyModel:\n    def decide(self): pass\n"
        chunks = chunk_stage_output("builder", text)
        assert len(chunks) == 1

    def test_unknown_stage_raises(self):
        with pytest.raises(ValueError, match="Unknown stage"):
            chunk_stage_output("unknown_stage", "some text")

    def test_empty_text_returns_empty(self):
        chunks = chunk_stage_output("researcher", "")
        assert chunks == []


# ---------------------------------------------------------------------------
# Indexing tests
# ---------------------------------------------------------------------------


def _make_extraction(
    *, facts: list[str] | None = None, stage: str = "researcher", run_id: str = "run-1"
) -> ExtractionResult:
    return ExtractionResult(
        nodes=[],
        relations=[],
        facts=facts or [],
        stage=stage,
        run_id=run_id,
    )


def _make_embedding_service(dim: int = 1024) -> AsyncMock:
    svc = AsyncMock()
    svc.embed_texts = AsyncMock(
        side_effect=lambda texts, input_type="document": [[0.1] * dim for _ in texts]
    )
    return svc


def _make_vector_store() -> AsyncMock:
    store = AsyncMock()
    store.upsert_dense = AsyncMock()
    store.upsert_sparse = AsyncMock()
    return store


class TestIndexStageOutput:
    """Tests for the main indexing pipeline."""

    @pytest.mark.asyncio
    async def test_researcher_report_artifacts_indexed(self):
        """AC1: Deep report sections are embedded and upserted to artifacts_dense + artifacts_sparse."""
        text = (
            "# Homeostatic Regulation\n\n"
            "## Foundations\nFoundational text about homeostasis and energy balance.\n\n"
            "## Postulates\nP1: Energy balance is maintained by hypothalamic circuits.\n"
            "P2: Ghrelin modulates hunger signals through the hypothalamus.\n\n"
            "## Assumptions\nWe assume normal human physiology.\n\n"
            "## Predictions\nGhrelin levels should predict subjective hunger ratings.\n\n"
            "## Variables\nEnergy level, hunger, ghrelin concentration, leptin.\n\n"
            "## References\nDoe 2020 DOI 10.1016/example. Smith 2021.\n"
        )
        extraction = _make_extraction(facts=[])
        embedding_svc = _make_embedding_service()
        vector_store = _make_vector_store()

        result = await index_stage_output(
            "researcher", text, extraction, embedding_svc, vector_store, "run-1"
        )

        assert isinstance(result, IndexResult)
        assert result.artifacts_indexed >= 5
        assert result.facts_indexed == 0
        # Dense and sparse upserts should have been called
        assert vector_store.upsert_dense.call_count >= 5
        assert vector_store.upsert_sparse.call_count >= 5
        # All dense upserts should go to artifacts_dense
        for call in vector_store.upsert_dense.call_args_list:
            assert (
                call.kwargs.get("collection", call.args[0] if call.args else None)
                == "artifacts_dense"
            )

    @pytest.mark.asyncio
    async def test_facts_indexed_to_memories(self):
        """AC2: Extracted facts are upserted as individual points to memories_dense + memories_sparse."""
        facts = [
            "Ghrelin modulates hunger signals through the hypothalamus.",
            "Leptin provides satiety feedback to the arcuate nucleus.",
            "Energy balance is maintained by homeostatic circuits.",
            "Dopamine mediates wanting but not liking.",
            "The lateral hypothalamus integrates hunger and reward signals.",
            "Insulin sensitivity affects glucose-dependent food intake.",
            "Orexin neurons in the LH promote wakefulness and feeding.",
            "NPY/AgRP neurons are activated by energy deficit.",
            "POMC neurons are activated by energy surplus.",
            "Circadian rhythms modulate hypothalamic hunger circuits.",
        ]
        extraction = _make_extraction(facts=facts)
        embedding_svc = _make_embedding_service()
        vector_store = _make_vector_store()

        result = await index_stage_output(
            "researcher", "", extraction, embedding_svc, vector_store, "run-1"
        )

        assert result.facts_indexed == 10
        # memories_dense and memories_sparse calls
        memories_dense_calls = [
            c
            for c in vector_store.upsert_dense.call_args_list
            if (c.kwargs.get("collection") or c.args[0]) == "memories_dense"
        ]
        memories_sparse_calls = [
            c
            for c in vector_store.upsert_sparse.call_args_list
            if (c.kwargs.get("collection") or c.args[0]) == "memories_sparse"
        ]
        assert len(memories_dense_calls) == 10
        assert len(memories_sparse_calls) == 10

    @pytest.mark.asyncio
    async def test_deterministic_ids_enable_idempotent_upsert(self):
        """AC5: Same run_id + stage produces same point IDs (deterministic UUID)."""
        text = "## Section\nSome content.\n"
        extraction = _make_extraction(facts=["A fact."])
        embedding_svc = _make_embedding_service()

        store1 = _make_vector_store()
        store2 = _make_vector_store()

        await index_stage_output(
            "researcher", text, extraction, embedding_svc, store1, "run-1"
        )
        await index_stage_output(
            "researcher", text, extraction, embedding_svc, store2, "run-1"
        )

        # Extract IDs from both runs
        ids1 = [
            c.kwargs.get("id") or c.args[1] for c in store1.upsert_dense.call_args_list
        ]
        ids2 = [
            c.kwargs.get("id") or c.args[1] for c in store2.upsert_dense.call_args_list
        ]
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_payload_contains_required_fields(self):
        """AC6: Payload includes entity_id, namespace, source_stage, run_id, importance, etc.

        After P3-002, `confidence` is no longer written to Qdrant payloads —
        Postgres is the single source of truth and is consulted at retrieve
        time. See docs/specs/memory-refactor/phase-3-data-integrity.md §R2.
        """
        text = "## Foundations\nSome content.\n"
        extraction = _make_extraction(facts=[])
        embedding_svc = _make_embedding_service()
        vector_store = _make_vector_store()

        await index_stage_output(
            "researcher", text, extraction, embedding_svc, vector_store, "run-1"
        )

        for call in (
            vector_store.upsert_dense.call_args_list[0],
            vector_store.upsert_sparse.call_args_list[0],
        ):
            payload = call.kwargs.get("payload") or call.args[3]
            assert "entity_id" in payload
            assert payload["namespace"] == "paradigm"
            assert payload["source_stage"] == "researcher"
            assert payload["run_id"] == "run-1"
            assert "importance" in payload
            assert "confidence" not in payload
            assert "created_at" in payload
            assert "text_preview" in payload
            assert len(payload["text_preview"]) <= 200

    @pytest.mark.asyncio
    async def test_namespace_inferred_from_stage(self):
        """Namespace mapping: researcher->paradigm, formalizer->formulation, reasoner->formulation, builder->model."""
        embedding_svc = _make_embedding_service()
        stage_text = {
            "researcher": "## Section\nContent.\n",
            "formalizer": "### Formulation 1: X\nY\n",
            "reasoner": '{"key": "val"}',
            "builder": "class Model: pass",
        }
        stage_ns = {
            "researcher": "paradigm",
            "formalizer": "formulation",
            "reasoner": "formulation",
            "builder": "model",
        }
        for stage, expected_ns in stage_ns.items():
            store = _make_vector_store()
            extraction = _make_extraction(stage=stage)

            await index_stage_output(
                stage, stage_text[stage], extraction, embedding_svc, store, "run-1"
            )

            if store.upsert_dense.call_count > 0:
                call = store.upsert_dense.call_args_list[0]
                payload = call.kwargs.get("payload") or call.args[3]
                assert payload["namespace"] == expected_ns, (
                    f"Stage {stage} should map to namespace {expected_ns}"
                )

    @pytest.mark.asyncio
    async def test_total_chunks_equals_artifacts_plus_facts(self):
        text = "## Section\nContent.\n"
        extraction = _make_extraction(facts=["Fact one.", "Fact two."])
        embedding_svc = _make_embedding_service()
        vector_store = _make_vector_store()

        result = await index_stage_output(
            "researcher", text, extraction, embedding_svc, vector_store, "run-1"
        )

        assert result.total_chunks == result.artifacts_indexed + result.facts_indexed

    @pytest.mark.asyncio
    async def test_empty_text_and_no_facts_returns_zero(self):
        extraction = _make_extraction(facts=[])
        embedding_svc = _make_embedding_service()
        vector_store = _make_vector_store()

        result = await index_stage_output(
            "researcher", "", extraction, embedding_svc, vector_store, "run-1"
        )

        assert result.artifacts_indexed == 0
        assert result.facts_indexed == 0
        assert result.total_chunks == 0
        embedding_svc.embed_texts.assert_not_called()

    @pytest.mark.asyncio
    async def test_confidence_never_written_to_payload(self):
        """P3-002: `confidence` is not written to Qdrant for any stage.

        Postgres `memories.confidence` is the single source of truth; the
        retrieval path batch-reads it at query time.
        """
        embedding_svc = _make_embedding_service()
        stage_text = {
            "researcher": "## Section\nX.\n",
            "formalizer": "### Formulation 1: X\nY\n",
            "reasoner": '{"k": "v"}',
            "builder": "class M: pass",
        }
        for stage in stage_text:
            store = _make_vector_store()
            extraction = _make_extraction(stage=stage)
            await index_stage_output(
                stage, stage_text[stage], extraction, embedding_svc, store, "run-1"
            )
            if store.upsert_dense.call_count > 0:
                call = store.upsert_dense.call_args_list[0]
                payload = call.kwargs.get("payload") or call.args[3]
                assert "confidence" not in payload, (
                    f"Stage {stage} payload still carries confidence"
                )

    @pytest.mark.asyncio
    async def test_embed_texts_count_mismatch_raises(self):
        """embed_texts returning fewer vectors than texts should raise RuntimeError."""
        text = "## Section One\nContent one.\n\n## Section Two\nContent two.\n\n## Section Three\nContent three.\n"
        extraction = _make_extraction(facts=[])
        vector_store = _make_vector_store()

        svc = AsyncMock()
        svc.embed_texts = AsyncMock(
            return_value=[[0.1] * 1024]
        )  # only 1 vector for 3 chunks

        with pytest.raises(
            RuntimeError, match="embed_texts returned 1 vectors for 3 texts"
        ):
            await index_stage_output(
                "researcher", text, extraction, svc, vector_store, "run-1"
            )

    def test_formalizer_no_headers_returns_empty(self):
        """Formalizer text without ### Formulation headers produces no chunks."""
        chunks = chunk_stage_output(
            "formalizer", "# Intro\nNo formulation headers here"
        )
        assert chunks == []

    def test_researcher_no_section_headers_returns_empty(self):
        """Researcher text without ## headers produces no chunks."""
        chunks = chunk_stage_output("researcher", "No section headers at all")
        assert chunks == []
