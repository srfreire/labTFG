"""Knowledge graph retrieval via entity linking and PPR traversal."""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from decisionlab.config import SETTINGS
from decisionlab.knowledge.retrieval.models import RetrievalResult
from decisionlab.knowledge.retrieval.query_rewriter import rewrite as _rewrite
from decisionlab.runtime.usage import record as record_usage
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph, vector_index_name
from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)


_FAST_MODEL = SETTINGS.knowledge_fast_model
_MAX_TOKENS = 512
_PPR_DECAY = 0.85
_SIMILARITY_THRESHOLD = 0.75

# Per-intent allowed relation types for PPR traversal. The intent is
# derived from the dominant linked-entity label in the query (paradigm
# vs. variable). Filtering trims hub-bridging edges that drag in
# unrelated regions of the graph.
_PARADIGM_INTENT_TYPES = ("SUPPORTS", "CONTRADICTS", "EXTENDS", "BELONGS_TO")
_VARIABLE_INTENT_TYPES = (
    "MEASURES",
    "MODULATES",
    "USES_VARIABLE",
    "HAS_PARAMETER",
    "GOVERNS",
)


def _types_for_intent(intent: str) -> tuple[str, ...]:
    """Map a query intent label to the set of allowed PPR relation types."""
    if intent == "variable":
        return _VARIABLE_INTENT_TYPES
    return _PARADIGM_INTENT_TYPES


def _score_node(*, confidence: float, hops: int, degree: int) -> float:
    """PPR score with hub-dampening:

        score = confidence * 0.85^hops / log(2 + degree)

    The log-degree term penalises high-degree hubs (e.g. "Brain" connected
    to everything) so a low-degree neighbour scoring 0.85 dominates a
    200-degree hub scoring 0.85.
    """
    decay = _PPR_DECAY**hops
    damp = 1.0 / math.log(2 + max(0, degree))
    return confidence * decay * damp


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
    "Equation": "latex",
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


async def _extract_entities(
    query: str,
    client: AsyncAnthropic,
    *,
    keyword_hints: list[str] | None = None,
) -> list[dict]:
    """Prompt Haiku to extract named entities from the query.

    When *keyword_hints* is given, prepend a 'Hint keywords: ...' line
    so the model is biased toward the rewriter's focal terms before it
    reads the raw question.

    Returns a list of dicts with 'name' and 'type' keys.
    """
    user_message = query
    if keyword_hints:
        hint_line = "Hint keywords: " + ", ".join(keyword_hints)
        user_message = f"{hint_line}\n\n{query}"

    for attempt in range(2):
        response = await client.messages.create(
            model=_FAST_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_NER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        record_usage(_FAST_MODEL, getattr(response, "usage", None))

        if getattr(response, "stop_reason", None) == "max_tokens":
            usage = getattr(response, "usage", None)
            out_tokens = getattr(usage, "output_tokens", None) if usage else None
            raise RuntimeError(
                f"KG NER output truncated at max_tokens={_MAX_TOKENS} "
                f"(output_tokens={out_tokens})"
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
    """Compute cosine similarity between two vectors. Retained as a
    public helper for tests and ad-hoc use; entity linking now goes
    through Qdrant ANN."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _link_entities_ann(
    label: str,
    name: str,
    embedding_service: EmbeddingService,
    kg: KnowledgeGraph,
    vectors: VectorStore | None,
) -> list[_LinkedEntity]:
    """Vector-index entity linking against the native Neo4j vector index.

    P4-002: replaces the prior Qdrant ``kg_entities_dense`` round-trip
    with a single ``db.index.vector.queryNodes`` Cypher call against the
    label's ``<label>_embedding_idx``. Returns elementId + display name
    in the same query — no second hop needed.

    Labels without a vector index (Equation, BrainRegion, Author, Paper,
    Parameter) return ``[]``. Hits scoring below ``_SIMILARITY_THRESHOLD``
    are discarded.
    """
    try:
        index_name = vector_index_name(label)
    except ValueError:
        return []

    # `_VECTOR_INDEX_LABELS` is broader than `_LABEL_NAME_PROP` (e.g.
    # Postulate/Formulation/Model carry vector indexes for write-side
    # use but aren't surfaced through NER). Without a name property to
    # display we can't build a useful `_LinkedEntity`; bail out.
    name_prop = _LABEL_NAME_PROP.get(label)
    if name_prop is None:
        return []

    query_vec = await embedding_service.embed_query(name)
    rows = await kg.query(
        "CALL db.index.vector.queryNodes($index_name, $k, $vector) "
        "YIELD node, score "
        f"WHERE '{label}' IN labels(node) "
        f"RETURN elementId(node) AS id, node.{name_prop} AS name, score",
        {"index_name": index_name, "k": 5, "vector": query_vec},
    )

    out: list[_LinkedEntity] = []
    for row in rows:
        score = float(row.get("score") or 0.0)
        if score < _SIMILARITY_THRESHOLD:
            continue
        out.append(
            _LinkedEntity(
                node_id=row["id"],
                label=label,
                name=row.get("name") or "",
                confidence=score,
            )
        )
    return out


async def _link_entities(
    entities: list[dict],
    kg: KnowledgeGraph,
    embedding_service: EmbeddingService,
    vectors: VectorStore | None,
) -> list[_LinkedEntity]:
    """Link extracted entities to existing Neo4j nodes.

    Strategy per entity:
    1. Exact match (case-insensitive) on the label's name property.
    2. If no exact match, vector-index ANN against the label's native
       Neo4j vector index (``<label>_embedding_idx``). Single Cypher
       call, no Qdrant round-trip.
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

        # --- ANN match against Neo4j vector index ---
        linked.extend(
            await _link_entities_ann(label, entity_name, embedding_service, kg, vectors)
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
    rel_memory_ids: list[str | None] | None = None


async def _ppr_traverse(
    linked: list[_LinkedEntity],
    kg: KnowledgeGraph,
    *,
    intent: str = "paradigm",
) -> list[_ScoredNode]:
    """Run 2-hop BFS from each linked entity with score decay.

    Two filters keep the traversal focused:

    - Relations are filtered to those relevant for the query intent
      (paradigm-style vs. variable-style) — see ``_types_for_intent``.
    - Per-node degree dampens hub influence — see ``_score_node``.

    For nodes reached by multiple paths, the maximum score wins.
    """
    allowed_types = list(_types_for_intent(intent))
    scored: dict[str, _ScoredNode] = {}

    def _update(
        node_id: str,
        row: dict,
        score: float,
        rels: list[str],
        rel_memory_ids: list[str | None] | None = None,
    ):
        if node_id not in scored or score > scored[node_id].score:
            scored[node_id] = _ScoredNode(
                node_id=node_id,
                labels=row["labels"],
                properties=row["props"],
                score=score,
                relation_chain=rels,
                rel_memory_ids=rel_memory_ids,
            )

    for entity in linked:
        # Include the seed node itself (hop 0). Score = confidence (no
        # decay or damp at hop 0 — the seed is the anchor).
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

        # 1-hop and 2-hop neighbours, filtered by allowed relation types.
        # Connected node degree (used for hub dampening) is computed
        # server-side via COUNT { (connected)--() }. Per P4-004 the
        # relation no longer carries `run_id` — `rel.memory_id` joins back
        # to the PG row that owns the per-run provenance.
        traversal_results = await kg.query(
            "MATCH path = (start)-[r*1..2]-(connected) "
            "WHERE elementId(start) = $start_id "
            "  AND ALL(rel IN r WHERE type(rel) IN $allowed_types) "
            "RETURN elementId(connected) AS id, "
            "labels(connected) AS labels, "
            "properties(connected) AS props, "
            "length(path) AS hops, "
            "[rel IN r | type(rel)] AS rel_types, "
            "[rel IN r | rel.memory_id] AS rel_memory_ids, "
            "COUNT { (connected)--() } AS degree",
            {"start_id": entity.node_id, "allowed_types": allowed_types},
        )

        for row in traversal_results:
            score = _score_node(
                confidence=entity.confidence,
                hops=int(row["hops"]),
                degree=int(row.get("degree") or 0),
            )
            _update(
                row["id"],
                row,
                score,
                row["rel_types"],
                rel_memory_ids=row.get("rel_memory_ids"),
            )

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
    results: list[RetrievalResult] = []
    for node in sorted_nodes[:limit]:
        meta = {
            "node_id": node.node_id,
            "labels": node.labels,
            "relation_chain": node.relation_chain,
        }
        # Run provenance comes from the new run_count / last_run_at properties
        # (memory-refactor P0-004). Per-run history lives in Postgres
        # ``node_run_observations`` and is fetched separately when needed.
        run_count = node.properties.get("run_count")
        if run_count:
            meta["run_count"] = run_count
        last_run_at = node.properties.get("last_run_at")
        if last_run_at:
            meta["last_run_at"] = last_run_at
        created_at = node.properties.get("created_at")
        if created_at:
            meta["run_date"] = created_at
            meta["created_at"] = created_at
        # Add relation-level memory_id provenance — callers can join through
        # ``pipeline_memories`` for run_id, valid_from/valid_to, confidence.
        if node.rel_memory_ids:
            meta["rel_memory_ids"] = node.rel_memory_ids
        results.append(
            RetrievalResult(
                text=_format_passage(node),
                score=node.score,
                source="kg",
                metadata=meta,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def kg_retrieve(
    query: str,
    kg: KnowledgeGraph,
    embedding_service: EmbeddingService,
    client: AsyncAnthropic,
    *,
    vectors: VectorStore | None,
    limit: int = 20,
) -> list[RetrievalResult]:
    """Retrieve knowledge graph passages relevant to a query.

    Pipeline: entity extraction (Haiku NER) → entity linking (exact + embedding)
    → PPR traversal (2-hop BFS with decay) → passage collection.

    Returns an empty list on any connection or service error so callers
    degrade gracefully.
    """
    try:
        # Step 0: Rewrite the query — focal_concept feeds the dense
        # path, keywords bias the NER prompt. Best-effort: a rewrite
        # failure falls back to passthrough inside `_rewrite` itself.
        rewritten = await _rewrite(query, client=client)

        # Step 1: Extract entities, hinting with the rewriter's keywords.
        entities = await _extract_entities(
            query, client, keyword_hints=rewritten.keywords or None
        )
        if not entities:
            logger.info("kg_retrieve: no entities extracted from query %r", query)
            return []

        # Step 2: Link entities to graph nodes.
        linked = await _link_entities(entities, kg, embedding_service, vectors)
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
