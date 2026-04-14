---
id: P3-001
title: Implement knowledge graph retrieval with entity linking and PPR traversal
status: todo
kind: strike
phase: 3
heat: retrieval
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-14
---

# P3-001: Implement knowledge graph retrieval with entity linking and PPR traversal

## Objective
Build the knowledge graph retrieval channel: extract entities from a query using Haiku, link them to existing Neo4j nodes via embedding similarity, then traverse the graph using Personalized PageRank (2-hop BFS approximation) to discover related passages and facts.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py`

- `async kg_retrieve(query: str, kg: KnowledgeGraph, embedding_service: EmbeddingService, client: AsyncAnthropic, limit: int = 20) -> list[RetrievalResult]`

- **Step 1: Entity extraction (Haiku NER)**
  - Prompt Haiku: "Extract named entities from this query that could appear in a scientific knowledge graph. Return JSON: {entities: [{name, type}]} where type is one of: paradigm, variable, brain_region, author, paper, equation, parameter"
  - Example: "How does ghrelin modulate hunger via the hypothalamus?" → `[{name: "ghrelin", type: "variable"}, {name: "hunger", type: "variable"}, {name: "hypothalamus", type: "brain_region"}]`

- **Step 2: Entity linking**
  - For each extracted entity, query Neo4j for nodes of matching label with similar names
  - Strategy: first try exact match (case-insensitive) on name/slug property. If no exact match, embed the entity name via Voyage AI and compare against stored node names (embed all candidate node names, cosine similarity, threshold > 0.75)
  - Return linked node IDs + labels

- **Step 3: PPR traversal (2-hop BFS with decay)**
  - From each linked node, traverse outgoing and incoming relations up to 2 hops
  - Score each discovered node: `score = base_score * decay^hop_distance` where base_score comes from entity linking confidence and decay = 0.85
  - For nodes reached by multiple paths, take the max score
  - Cypher query pattern:
    ```cypher
    MATCH path = (start)-[*1..2]-(connected)
    WHERE elementId(start) = $start_id
    RETURN connected, length(path) as hops, relationships(path) as rels
    ```

- **Step 4: Passage collection**
  - For each high-scoring discovered node, collect its properties as a text passage
  - Format: include node label, key properties, and the relation chain that led to it
  - Example passage: "Variable 'ghrelin' (type: state, range: [0,100]) —MODULATES→ Variable 'hunger' (direction: positive) —MEASURES→ BrainRegion 'hypothalamus' (system: homeostatic)"

- `RetrievalResult` dataclass (shared across all retrieval channels):
  ```python
  @dataclass
  class RetrievalResult:
      text: str              # the passage content
      score: float           # retrieval score (0-1)
      source: str            # "kg", "dense", "sparse", "web"
      metadata: dict         # node_ids, relation_types, run_id, etc.
  ```

## Acceptance Criteria
- [ ] AC1: Query "ghrelin hunger signaling" against a populated KG extracts entities "ghrelin" and "hunger", links them to Variable nodes, and returns passages describing their relationship
- [ ] AC2: Multi-hop discovery works: querying "dopamine" returns not just the Variable node but also connected BrainRegion (VTA, Nucleus Accumbens) and related Paradigm (hedonic, incentive salience) via 2-hop traversal
- [ ] AC3: Entity linking handles case variations: "Berridge" matches Author node "Berridge, Kent C."
- [ ] AC4: Entity linking handles partial matches via embedding similarity: "reward learning" links to Paradigm "hedonic-reward-based-regulation"
- [ ] AC5: Scores decrease with hop distance: direct matches score higher than 2-hop discoveries
- [ ] AC6: Returns empty list gracefully when no entities are found or no nodes match

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/retrieval/__init__.py` — new subpackage
- `phase1-pablo/src/decisionlab/knowledge/retrieval/kg_retrieval.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/retrieval/models.py` — RetrievalResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-3-retrieval-crag.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `retrieval`
Uses `KnowledgeGraph` client from P1-001 and `EmbeddingService` from P1-004.
