"""Tests for the Phase D Canonicalizer.

Covers the merge / keep-separate paths plus the key remapping that
follows an approved merge. Embedding and KG access are mocked so the
test is hermetic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.canonicalize import canonicalize
from decisionlab.knowledge.models import ExtractionResult, NodeSpec, RelationSpec


def _mock_kg(by_label: dict[str, list[dict]] | None = None):
    """Build a KG mock whose query() returns rows matching the requested label."""
    by_label = by_label or {}
    kg = MagicMock()
    kg.unique_key_for = MagicMock(
        side_effect=lambda lab: {
            "Paradigm": "slug",
            "Variable": "name",
            "Postulate": "id",
        }.get(lab, "name")
    )

    async def _query(cypher, params=None):
        # The cypher always includes "MATCH (n:<Label>)" — extract the label.
        for label, rows in by_label.items():
            if f":{label})" in cypher:
                return rows
        return []

    kg.query = AsyncMock(side_effect=_query)
    return kg


def _mock_emb(vectors: list[list[float]]):
    emb = MagicMock()
    emb.embed_texts = AsyncMock(return_value=vectors)
    return emb


def _mock_client_verify(*, merge: bool, reason: str = "test"):
    """Mock Anthropic client whose forced tool-use call returns a
    _MergeVerification verdict."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit__MergeVerification"
    block.input = {"merge": merge, "reason": reason}

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.usage = None

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_canonicalize_no_kg_returns_input_unchanged():
    """When KG or embedding service is None, canonicalize is a no-op."""
    extraction = ExtractionResult(
        nodes=[
            NodeSpec(
                label="Paradigm",
                properties={
                    "slug": "rl",
                    "name": "RL",
                    "description": "learn from reward",
                },
                natural_key="slug",
            )
        ],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    out = await canonicalize(
        extraction, kg=None, embedding_service=None, client=MagicMock()
    )
    assert out is extraction


@pytest.mark.asyncio
async def test_canonicalize_below_threshold_keeps_separate():
    """Cosine similarity below τ leaves the candidate in the extraction."""
    candidate = NodeSpec(
        label="Paradigm",
        properties={
            "slug": "q-learning",
            "name": "Q-learning",
            "description": "TD methods",
        },
        natural_key="slug",
    )
    extraction = ExtractionResult(
        nodes=[candidate],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    kg = _mock_kg(
        {
            "Paradigm": [
                {
                    "slug": "prospect-theory",
                    "name": "Prospect",
                    "description": "risk",
                    "_key": "prospect-theory",
                }
            ]
        }
    )
    # Orthogonal vectors → cosine 0.0, well below 0.85.
    emb = _mock_emb([[1.0, 0.0], [0.0, 1.0]])
    client = _mock_client_verify(merge=True)  # would approve, but cosine vetoes

    out = await canonicalize(extraction, kg=kg, embedding_service=emb, client=client)
    assert len(out.nodes) == 1
    assert out.nodes[0].properties["slug"] == "q-learning"
    # LLM never called because we never crossed the threshold.
    client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_canonicalize_merge_remaps_relations():
    """Approved merge drops the duplicate node and rewrites relation endpoints."""
    candidate = NodeSpec(
        label="Paradigm",
        properties={
            "slug": "q-learning",
            "name": "Q-learning",
            "description": "Reward-based learning via temporal difference updates",
        },
        natural_key="slug",
    )
    other = NodeSpec(
        label="Postulate",
        properties={"id": "P1", "statement": "rewards drive behaviour"},
        natural_key="id",
    )
    relation = RelationSpec(
        from_label="Postulate",
        from_key_value="P1",
        to_label="Paradigm",
        to_key_value="q-learning",  # this should be remapped to canonical
        rel_type="BELONGS_TO",
        properties={},
    )
    extraction = ExtractionResult(
        nodes=[candidate, other],
        relations=[relation],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    kg = _mock_kg(
        {
            "Paradigm": [
                {
                    "slug": "reinforcement-learning",
                    "name": "Reinforcement Learning",
                    "description": "Reward-based learning paradigm",
                    "_key": "reinforcement-learning",
                }
            ]
        }
    )
    # Identical vectors → cosine 1.0 → above τ.
    emb = _mock_emb([[1.0, 0.0], [1.0, 0.0]])
    client = _mock_client_verify(merge=True, reason="same paradigm")

    out = await canonicalize(extraction, kg=kg, embedding_service=emb, client=client)

    # Paradigm node was merged → only the Postulate remains.
    paradigm_nodes = [n for n in out.nodes if n.label == "Paradigm"]
    assert paradigm_nodes == []
    postulate_nodes = [n for n in out.nodes if n.label == "Postulate"]
    assert len(postulate_nodes) == 1

    # Relation endpoint rewritten to canonical slug.
    assert len(out.relations) == 1
    assert out.relations[0].to_key_value == "reinforcement-learning"
    assert out.relations[0].from_key_value == "P1"


@pytest.mark.asyncio
async def test_canonicalize_llm_says_keep_separate():
    """Cosine above τ but the LLM verifier rejects merge → no remap."""
    candidate = NodeSpec(
        label="Paradigm",
        properties={
            "slug": "drift-diffusion-model",
            "name": "Drift-Diffusion Model",
            "description": "Evidence accumulation in two-alternative forced choice",
        },
        natural_key="slug",
    )
    extraction = ExtractionResult(
        nodes=[candidate],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    kg = _mock_kg(
        {
            "Paradigm": [
                {
                    "slug": "race-model",
                    "name": "Race Model",
                    "description": "Independent accumulator decision model",
                    "_key": "race-model",
                }
            ]
        }
    )
    emb = _mock_emb([[1.0, 0.0], [0.95, 0.05]])  # very high cosine
    client = _mock_client_verify(
        merge=False, reason="DDM and race models have distinct architectures"
    )

    out = await canonicalize(extraction, kg=kg, embedding_service=emb, client=client)
    assert len(out.nodes) == 1
    assert out.nodes[0].properties["slug"] == "drift-diffusion-model"
    client.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_canonicalize_skips_label_when_kg_query_fails():
    """A KG query failure for one label doesn't poison the rest of the run."""
    candidate = NodeSpec(
        label="Paradigm",
        properties={"slug": "rl", "name": "RL", "description": "reward-driven"},
        natural_key="slug",
    )
    extraction = ExtractionResult(
        nodes=[candidate],
        relations=[],
        facts=[],
        stage="researcher",
        run_id="run-1",
    )
    kg = MagicMock()
    kg.unique_key_for = MagicMock(return_value="slug")
    kg.query = AsyncMock(side_effect=RuntimeError("Neo4j unreachable"))
    emb = _mock_emb([])

    out = await canonicalize(
        extraction, kg=kg, embedding_service=emb, client=MagicMock()
    )
    assert out.nodes == extraction.nodes
