"""Knowledge graph retrieval via entity linking and PPR traversal."""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph

from decisionlab.knowledge.retrieval.models import RetrievalResult

logger = logging.getLogger(__name__)

_HAIKU_MODEL = "claude-haiku-4-5"
_HAIKU_MAX_TOKENS = 512
_PPR_DECAY = 0.85
_SIMILARITY_THRESHOLD = 0.75

# Maps entity types from Haiku NER to Neo4j node labels.
_TYPE_TO_LABEL: dict[str, str] = {
    "paradigm": "Paradigm",
    "variable": "Variable",
    "brain_region": "BrainRegion",
    "author": "Author",
    "paper": "Paper",
    "equation": "Equation",
    "parameter": "Parameter",
}

# The primary name property per label (used for exact-match lookups).
_LABEL_NAME_PROP: dict[str, str] = {
    "Paradigm": "name",
    "Variable": "name",
    "BrainRegion": "name",
    "Author": "name",
    "Paper": "title",
    "Equation": "plaintext",
    "Parameter": "name",
}

_NER_SYSTEM_PROMPT = """\
Extract named entities from the user's query that could appear in a scientific \
knowledge graph about decision-making paradigms.

Return ONLY a JSON object (no markdown, no explanation outside JSON):
{"entities": [{"name": "<entity>", "type": "<type>"}]}

Valid types: paradigm, variable, brain_region, author, paper, equation, parameter

Examples:
Query: "How does ghrelin modulate hunger via the hypothalamus?"
{"entities": [{"name": "ghrelin", "type": "variable"}, {"name": "hunger", "type": "variable"}, {"name": "hypothalamus", "type": "brain_region"}]}

Query: "Berridge's incentive salience theory of dopamine"
{"entities": [{"name": "Berridge", "type": "author"}, {"name": "incentive salience", "type": "paradigm"}, {"name": "dopamine", "type": "variable"}]}

If no entities can be extracted, return: {"entities": []}
"""


@dataclass(frozen=True)
class _LinkedEntity:
    """An extracted entity linked to a Neo4j node."""

    node_id: str
    label: str
    name: str
    confidence: float


# ---------------------------------------------------------------------------
# Step 1: Entity extraction (Haiku NER)
# ---------------------------------------------------------------------------


async def _extract_entities(query: str, client: AsyncAnthropic) -> list[dict]:
    """Prompt Haiku to extract named entities from the query.

    Returns a list of dicts with 'name' and 'type' keys.
    """
    for attempt in range(2):
        response = await client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=_HAIKU_MAX_TOKENS,
            system=_NER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        raw = "\n".join(b.text for b in response.content if b.type == "text").strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
        cleaned = fence_match.group(1).strip() if fence_match else raw

        try:
            data = json.loads(cleaned)
            entities = data.get("entities", [])
            return [
                {"name": ent["name"], "type": ent["type"]}
                for ent in entities
                if isinstance(ent, dict)
                and "name" in ent
                and "type" in ent
                and ent["type"] in _TYPE_TO_LABEL
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            if attempt == 0:
                logger.warning(
                    "_extract_entities: parse failed attempt 1, retrying. "
                    "raw=%r exc=%s",
                    raw,
                    exc,
                )
                continue
            logger.error("_extract_entities: failed after 2 attempts. raw=%r", raw)
            return []

    return []  # unreachable, satisfies type checker


# ---------------------------------------------------------------------------
# Step 2: Entity linking
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _link_entities(
    entities: list[dict],
    kg: KnowledgeGraph,
    embedding_service: EmbeddingService,
) -> list[_LinkedEntity]:
    """Link extracted entities to existing Neo4j nodes.

    Strategy per entity:
    1. Exact match (case-insensitive) on the label's name property.
    2. If no exact match, embed the entity name and compare against
       all nodes of that label via cosine similarity (threshold > 0.75).
    """
    linked: list[_LinkedEntity] = []

    for ent in entities:
        label = _TYPE_TO_LABEL[ent["type"]]
        name_prop = _LABEL_NAME_PROP[label]
        entity_name: str = ent["name"]

        # --- Try exact match (case-insensitive) ---
        exact_results = await kg.query(
            f"MATCH (n:{label}) "
            f"WHERE toLower(n.{name_prop}) = toLower($name) "
            f"RETURN elementId(n) AS id, n.{name_prop} AS name",
            {"name": entity_name},
        )
        if exact_results:
            row = exact_results[0]
            linked.append(
                _LinkedEntity(
                    node_id=row["id"],
                    label=label,
                    name=row["name"],
                    confidence=1.0,
                )
            )
            continue

        # --- Fuzzy match via embedding similarity ---
        all_candidates = await kg.query(
            f"MATCH (n:{label}) RETURN elementId(n) AS id, n.{name_prop} AS name",
        )
        if not all_candidates:
            continue

        # Filter out candidates with null/empty names to keep indices aligned.
        candidates = [c for c in all_candidates if c["name"]]
        if not candidates:
            continue

        candidate_names = [c["name"] for c in candidates]
        query_vec = await embedding_service.embed_query(entity_name)
        candidate_vecs = await embedding_service.embed_texts(candidate_names)

        similarities = [_cosine_similarity(query_vec, cvec) for cvec in candidate_vecs]
        best_idx = max(range(len(similarities)), key=lambda i: similarities[i])
        best_sim = similarities[best_idx]

        if best_sim >= _SIMILARITY_THRESHOLD:
            matched = candidates[best_idx]
            linked.append(
                _LinkedEntity(
                    node_id=matched["id"],
                    label=label,
                    name=matched["name"],
                    confidence=best_sim,
                )
            )

    return linked


# ---------------------------------------------------------------------------
# Step 3: PPR traversal (2-hop BFS with decay)
# ---------------------------------------------------------------------------


@dataclass
class _ScoredNode:
    """A node discovered during PPR traversal."""

    node_id: str
    labels: list[str]
    properties: dict
    score: float
    relation_chain: list[str]


async def _ppr_traverse(
    linked: list[_LinkedEntity], kg: KnowledgeGraph
) -> list[_ScoredNode]:
    """Run 2-hop BFS from each linked entity with score decay.

    Score = base_confidence * 0.85^hops.  For nodes reached by multiple
    paths, keep the maximum score.
    """
    scored: dict[str, _ScoredNode] = {}

    def _update(node_id: str, row: dict, score: float, rels: list[str]):
        if node_id not in scored or score > scored[node_id].score:
            scored[node_id] = _ScoredNode(
                node_id=node_id,
                labels=row["labels"],
                properties=row["props"],
                score=score,
                relation_chain=rels,
            )

    for entity in linked:
        # Include the seed node itself (hop 0).
        seed_results = await kg.query(
            "MATCH (n) WHERE elementId(n) = $id "
            "RETURN elementId(n) AS id, labels(n) AS labels, "
            "properties(n) AS props",
            {"id": entity.node_id},
        )
        if seed_results:
            row = seed_results[0]
            _update(row["id"], row, entity.confidence, [])
        else:
            logger.warning(
                "_ppr_traverse: seed node %s (%s) not found in graph",
                entity.node_id,
                entity.name,
            )
            continue

        # 1-hop and 2-hop neighbors.
        traversal_results = await kg.query(
            "MATCH path = (start)-[*1..2]-(connected) "
            "WHERE elementId(start) = $start_id "
            "RETURN elementId(connected) AS id, "
            "labels(connected) AS labels, "
            "properties(connected) AS props, "
            "length(path) AS hops, "
            "[r IN relationships(path) | type(r)] AS rel_types",
            {"start_id": entity.node_id},
        )

        for row in traversal_results:
            score = entity.confidence * (_PPR_DECAY ** row["hops"])
            _update(row["id"], row, score, row["rel_types"])

    return list(scored.values())


# ---------------------------------------------------------------------------
# Step 4: Passage collection
# ---------------------------------------------------------------------------


def _format_passage(node: _ScoredNode) -> str:
    """Format a scored node into a human-readable passage."""
    label = node.labels[0] if node.labels else "Node"
    skip_keys = {"embedding", "vector"}
    props_str = ", ".join(
        f"{k}: {v}"
        for k, v in node.properties.items()
        if k not in skip_keys and v is not None
    )

    passage = f"{label} ({props_str})"
    if node.relation_chain:
        passage = f"{passage} [via {' -> '.join(node.relation_chain)}]"
    return passage


def _collect_passages(
    scored_nodes: list[_ScoredNode], limit: int
) -> list[RetrievalResult]:
    """Convert scored nodes into RetrievalResult list, sorted by score."""
    sorted_nodes = sorted(scored_nodes, key=lambda n: n.score, reverse=True)
    return [
        RetrievalResult(
            text=_format_passage(node),
            score=node.score,
            source="kg",
            metadata={
                "node_id": node.node_id,
                "labels": node.labels,
                "relation_chain": node.relation_chain,
            },
        )
        for node in sorted_nodes[:limit]
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def kg_retrieve(
    query: str,
    kg: KnowledgeGraph,
    embedding_service: EmbeddingService,
    client: AsyncAnthropic,
    limit: int = 20,
) -> list[RetrievalResult]:
    """Retrieve knowledge graph passages relevant to a query.

    Pipeline: entity extraction (Haiku NER) → entity linking (exact + embedding)
    → PPR traversal (2-hop BFS with decay) → passage collection.

    Returns an empty list on any connection or service error so callers
    degrade gracefully.
    """
    try:
        # Step 1: Extract entities.
        entities = await _extract_entities(query, client)
        if not entities:
            logger.info("kg_retrieve: no entities extracted from query %r", query)
            return []

        # Step 2: Link entities to graph nodes.
        linked = await _link_entities(entities, kg, embedding_service)
        if not linked:
            logger.info(
                "kg_retrieve: no entities linked for query %r (extracted: %s)",
                query,
                entities,
            )
            return []

        # Step 3: PPR traversal.
        scored_nodes = await _ppr_traverse(linked, kg)

        # Step 4: Collect passages.
        return _collect_passages(scored_nodes, limit)

    except Exception as exc:
        logger.error("kg_retrieve failed: %s", exc)
        return []
