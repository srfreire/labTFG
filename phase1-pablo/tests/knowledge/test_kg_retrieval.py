"""Tests for KG retrieval with entity linking and PPR traversal.

Unit tests use mocked KnowledgeGraph, EmbeddingService, and AsyncAnthropic
to verify each step of the pipeline without live services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.retrieval.kg_retrieval import (
    _collect_passages,
    _cosine_similarity,
    _extract_entities,
    _link_entities,
    _LinkedEntity,
    _ppr_traverse,
    _score_node,
    _ScoredNode,
    kg_retrieve,
)
from decisionlab.knowledge.retrieval.models import RetrievalResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_haiku_response(json_str: str) -> MagicMock:
    """Build a mock Anthropic response with the given text content."""
    block = MagicMock()
    block.type = "text"
    block.text = json_str
    resp = MagicMock()
    resp.content = [block]
    return resp


def _mock_client(json_str: str) -> AsyncMock:
    """Return a mock AsyncAnthropic whose messages.create returns json_str."""
    client = AsyncMock()
    client.messages.create = AsyncMock(return_value=_make_haiku_response(json_str))
    return client


# ---------------------------------------------------------------------------
# Step 1: Entity extraction
# ---------------------------------------------------------------------------


class TestExtractEntities:
    @pytest.mark.asyncio
    async def test_extracts_valid_entities(self):
        client = _mock_client(
            '{"entities": [{"name": "ghrelin", "type": "variable"}, '
            '{"name": "hunger", "type": "variable"}]}'
        )
        result = await _extract_entities("ghrelin hunger signaling", client)
        assert len(result) == 2
        assert result[0] == {"name": "ghrelin", "type": "variable"}
        assert result[1] == {"name": "hunger", "type": "variable"}

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        client = _mock_client(
            '```json\n{"entities": [{"name": "dopamine", "type": "variable"}]}\n```'
        )
        result = await _extract_entities("dopamine pathways", client)
        assert len(result) == 1
        assert result[0]["name"] == "dopamine"

    @pytest.mark.asyncio
    async def test_filters_unknown_types(self):
        client = _mock_client(
            '{"entities": [{"name": "x", "type": "variable"}, '
            '{"name": "y", "type": "unknown_type"}]}'
        )
        result = await _extract_entities("test", client)
        assert len(result) == 1
        assert result[0]["name"] == "x"

    @pytest.mark.asyncio
    async def test_returns_empty_on_bad_json(self):
        client = _mock_client("not json at all")
        # Second attempt also fails
        client.messages.create = AsyncMock(
            return_value=_make_haiku_response("still not json")
        )
        result = await _extract_entities("test", client)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_entities(self):
        client = _mock_client('{"entities": []}')
        result = await _extract_entities("hello world", client)
        assert result == []


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _cosine_similarity([0, 0], [1, 1]) == 0.0

    def test_similar_vectors(self):
        sim = _cosine_similarity([1.0, 2.0, 3.0], [1.1, 2.1, 3.1])
        assert sim > 0.99


# ---------------------------------------------------------------------------
# Step 2: Entity linking
# ---------------------------------------------------------------------------


class TestLinkEntities:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        kg = AsyncMock()
        kg.query = AsyncMock(return_value=[{"id": "4:abc", "name": "ghrelin"}])
        embedding = AsyncMock()

        entities = [{"name": "ghrelin", "type": "variable"}]
        result = await _link_entities(entities, kg, embedding, None)

        assert len(result) == 1
        assert result[0].node_id == "4:abc"
        assert result[0].label == "Variable"
        assert result[0].confidence == 1.0
        # Should not call embedding service for exact match
        embedding.embed_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_case_insensitive_exact_match(self):
        """AC3: 'Berridge' matches 'Berridge, Kent C.' via toLower."""
        kg = AsyncMock()
        kg.query = AsyncMock(
            return_value=[{"id": "4:berridge", "name": "Berridge, Kent C."}]
        )
        embedding = AsyncMock()

        entities = [{"name": "Berridge", "type": "author"}]
        result = await _link_entities(entities, kg, embedding, None)

        assert len(result) == 1
        assert result[0].name == "Berridge, Kent C."
        assert result[0].confidence == 1.0


# ANN-backed fuzzy matching is exercised in tests/knowledge/retrieval/
# test_kg_link_entities_ann.py — the prior table-scan + Python-cosine
# tests were deleted with the implementation they targeted.

# ---------------------------------------------------------------------------
# Step 3: PPR traversal
# ---------------------------------------------------------------------------


class TestPprTraverse:
    @pytest.mark.asyncio
    async def test_seed_node_included_at_full_score(self):
        kg = AsyncMock()
        kg.query = AsyncMock(
            side_effect=[
                # Seed node query
                [
                    {
                        "id": "4:seed",
                        "labels": ["Variable"],
                        "props": {"name": "ghrelin"},
                    }
                ],
                # Traversal returns nothing
                [],
            ]
        )
        linked = [
            _LinkedEntity(
                node_id="4:seed",
                label="Variable",
                name="ghrelin",
                confidence=1.0,
            )
        ]
        result = await _ppr_traverse(linked, kg)
        assert len(result) == 1
        assert result[0].score == 1.0
        assert result[0].node_id == "4:seed"

    @pytest.mark.asyncio
    async def test_scores_decrease_with_hops(self):
        """AC5: Direct matches score higher than 2-hop discoveries."""
        kg = AsyncMock()
        kg.query = AsyncMock(
            side_effect=[
                # Seed
                [
                    {
                        "id": "4:seed",
                        "labels": ["Variable"],
                        "props": {"name": "dopamine"},
                    }
                ],
                # Traversal: 1-hop and 2-hop neighbors. degree=10 mocks
                # a moderate-degree node; the absolute scores are derived
                # via _score_node so the test stays in lock-step with
                # whatever scoring formula the implementation uses.
                [
                    {
                        "id": "4:hop1",
                        "labels": ["BrainRegion"],
                        "props": {"name": "VTA"},
                        "hops": 1,
                        "rel_types": ["MEASURES"],
                        "degree": 10,
                    },
                    {
                        "id": "4:hop2",
                        "labels": ["Paradigm"],
                        "props": {"name": "hedonic"},
                        "hops": 2,
                        "rel_types": ["MEASURES", "BELONGS_TO"],
                        "degree": 10,
                    },
                ],
            ]
        )
        linked = [
            _LinkedEntity(
                node_id="4:seed",
                label="Variable",
                name="dopamine",
                confidence=1.0,
            )
        ]
        result = await _ppr_traverse(linked, kg)

        scores = {n.node_id: n.score for n in result}
        assert scores["4:seed"] > scores["4:hop1"] > scores["4:hop2"]
        assert scores["4:hop1"] == pytest.approx(
            _score_node(confidence=1.0, hops=1, degree=10)
        )
        assert scores["4:hop2"] == pytest.approx(
            _score_node(confidence=1.0, hops=2, degree=10)
        )

    @pytest.mark.asyncio
    async def test_multi_path_takes_max_score(self):
        """Node reached by multiple paths keeps max score."""
        kg = AsyncMock()
        kg.query = AsyncMock(
            side_effect=[
                # Seed 1
                [
                    {
                        "id": "4:s1",
                        "labels": ["Variable"],
                        "props": {"name": "a"},
                    }
                ],
                # Traversal from seed 1 — shared node at 2 hops
                [
                    {
                        "id": "4:shared",
                        "labels": ["BrainRegion"],
                        "props": {"name": "hypo"},
                        "hops": 2,
                        "rel_types": ["MEASURES", "MODULATES"],
                        "degree": 5,
                    },
                ],
                # Seed 2
                [
                    {
                        "id": "4:s2",
                        "labels": ["Variable"],
                        "props": {"name": "b"},
                    }
                ],
                # Traversal from seed 2 — same shared node at 1 hop
                [
                    {
                        "id": "4:shared",
                        "labels": ["BrainRegion"],
                        "props": {"name": "hypo"},
                        "hops": 1,
                        "rel_types": ["MEASURES"],
                        "degree": 5,
                    },
                ],
            ]
        )
        linked = [
            _LinkedEntity("4:s1", "Variable", "a", 1.0),
            _LinkedEntity("4:s2", "Variable", "b", 1.0),
        ]
        result = await _ppr_traverse(linked, kg)

        shared = [n for n in result if n.node_id == "4:shared"]
        assert len(shared) == 1
        # Max-score wins: 1-hop > 2-hop (both at the same degree).
        assert shared[0].score == pytest.approx(
            _score_node(confidence=1.0, hops=1, degree=5)
        )


# ---------------------------------------------------------------------------
# Step 4: Passage collection
# ---------------------------------------------------------------------------


class TestCollectPassages:
    def test_sorted_by_score_desc(self):
        nodes = [
            _ScoredNode("4:a", ["Variable"], {"name": "x"}, 0.5, []),
            _ScoredNode("4:b", ["Variable"], {"name": "y"}, 0.9, []),
            _ScoredNode("4:c", ["Variable"], {"name": "z"}, 0.7, []),
        ]
        results = _collect_passages(nodes, limit=10)
        assert results[0].score == 0.9
        assert results[1].score == 0.7
        assert results[2].score == 0.5

    def test_respects_limit(self):
        nodes = [
            _ScoredNode(f"4:{i}", ["V"], {"name": f"n{i}"}, float(i), [])
            for i in range(10)
        ]
        results = _collect_passages(nodes, limit=3)
        assert len(results) == 3

    def test_includes_relation_chain_in_passage(self):
        node = _ScoredNode(
            "4:a",
            ["BrainRegion"],
            {"name": "VTA", "system": "hedonic"},
            0.85,
            ["MEASURES", "BELONGS_TO"],
        )
        results = _collect_passages([node], limit=10)
        assert "via MEASURES -> BELONGS_TO" in results[0].text
        assert results[0].source == "kg"

    def test_passage_format(self):
        node = _ScoredNode(
            "4:a",
            ["Variable"],
            {"name": "ghrelin", "type": "state", "range": "[0,100]"},
            1.0,
            [],
        )
        results = _collect_passages([node], limit=10)
        assert "Variable" in results[0].text
        assert "ghrelin" in results[0].text
        assert results[0].metadata["node_id"] == "4:a"


# ---------------------------------------------------------------------------
# Full pipeline: kg_retrieve
# ---------------------------------------------------------------------------


class TestKgRetrieve:
    @pytest.mark.asyncio
    async def test_empty_entities_returns_empty(self):
        """AC6: Returns empty list when no entities are found."""
        client = _mock_client('{"entities": []}')
        kg = AsyncMock()
        embedding = AsyncMock()

        result = await kg_retrieve("hello world", kg, embedding, client, vectors=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_linked_entities_returns_empty(self):
        """AC6: Returns empty list when no nodes match."""
        client = _mock_client(
            '{"entities": [{"name": "nonexistent", "type": "variable"}]}'
        )
        kg = AsyncMock()
        kg.query = AsyncMock(side_effect=[[], []])
        embedding = AsyncMock()

        result = await kg_retrieve("test", kg, embedding, client, vectors=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """AC1: Full pipeline extracts, links, traverses, collects."""
        client = _mock_client(
            '{"entities": [{"name": "ghrelin", "type": "variable"}, '
            '{"name": "hunger", "type": "variable"}]}'
        )
        kg = AsyncMock()
        kg.query = AsyncMock(
            side_effect=[
                # Entity linking: exact match for "ghrelin"
                [{"id": "4:ghrelin", "name": "ghrelin"}],
                # Entity linking: exact match for "hunger"
                [{"id": "4:hunger", "name": "hunger"}],
                # PPR: seed node for ghrelin
                [
                    {
                        "id": "4:ghrelin",
                        "labels": ["Variable"],
                        "props": {"name": "ghrelin", "type": "state"},
                    }
                ],
                # PPR: traversal from ghrelin
                [
                    {
                        "id": "4:hunger",
                        "labels": ["Variable"],
                        "props": {"name": "hunger", "type": "state"},
                        "hops": 1,
                        "rel_types": ["MODULATES"],
                    },
                    {
                        "id": "4:hypo",
                        "labels": ["BrainRegion"],
                        "props": {
                            "name": "hypothalamus",
                            "system": "homeostatic",
                        },
                        "hops": 2,
                        "rel_types": ["MODULATES", "MEASURES"],
                    },
                ],
                # PPR: seed node for hunger
                [
                    {
                        "id": "4:hunger",
                        "labels": ["Variable"],
                        "props": {"name": "hunger", "type": "state"},
                    }
                ],
                # PPR: traversal from hunger
                [
                    {
                        "id": "4:ghrelin",
                        "labels": ["Variable"],
                        "props": {"name": "ghrelin", "type": "state"},
                        "hops": 1,
                        "rel_types": ["MODULATES"],
                    },
                ],
            ]
        )
        embedding = AsyncMock()

        results = await kg_retrieve(
            "ghrelin hunger signaling", kg, embedding, client, vectors=None
        )

        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert all(r.source == "kg" for r in results)
        # Scores should be sorted descending
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_multi_hop_discovery(self):
        """AC2: Multi-hop returns connected nodes beyond direct matches."""
        client = _mock_client(
            '{"entities": [{"name": "dopamine", "type": "variable"}]}'
        )
        kg = AsyncMock()
        kg.query = AsyncMock(
            side_effect=[
                # Exact match for dopamine
                [{"id": "4:dopa", "name": "dopamine"}],
                # Seed node
                [
                    {
                        "id": "4:dopa",
                        "labels": ["Variable"],
                        "props": {"name": "dopamine"},
                    }
                ],
                # Traversal: VTA at 1 hop, hedonic at 2 hops
                [
                    {
                        "id": "4:vta",
                        "labels": ["BrainRegion"],
                        "props": {"name": "VTA"},
                        "hops": 1,
                        "rel_types": ["MEASURES"],
                    },
                    {
                        "id": "4:nacc",
                        "labels": ["BrainRegion"],
                        "props": {"name": "Nucleus Accumbens"},
                        "hops": 1,
                        "rel_types": ["MEASURES"],
                    },
                    {
                        "id": "4:hedonic",
                        "labels": ["Paradigm"],
                        "props": {"name": "hedonic"},
                        "hops": 2,
                        "rel_types": ["MEASURES", "BELONGS_TO"],
                    },
                ],
            ]
        )
        embedding = AsyncMock()

        results = await kg_retrieve(
            "dopamine", kg, embedding, client, vectors=None, limit=20
        )

        texts = " ".join(r.text for r in results)
        assert "VTA" in texts
        assert "Nucleus Accumbens" in texts
        assert "hedonic" in texts
