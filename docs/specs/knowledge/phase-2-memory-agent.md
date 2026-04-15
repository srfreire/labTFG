# Phase 2: Memory Agent & Knowledge Extraction

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Build the Memory Agent — a dedicated agent that runs after every pipeline stage, extracts structured knowledge (entities, relations, facts), populates Neo4j and Qdrant, scores importance, resolves conflicts with existing memories, and creates provenance edges. This is the write path of the knowledge backbone.

## Requirements

### R1: Entity & Relation Extraction Module
- LLM-based extraction using Haiku (`claude-haiku-4-5`)
- Stage-specific extraction prompts that understand each stage's output format:
  - **After Researcher/DeepResearcher:** extract Paradigm, Author, Paper (with DOI/year/citations from Semantic Scholar data), BrainRegion, Variable, Postulate entities. Extract BELONGS_TO, AUTHORED, SUPPORTS, MEASURES relations.
  - **After Formalizer:** extract Equation, Variable, Parameter entities. Extract USES_EQUATION, MODULATES relations. Link formulations to paradigms.
  - **After Reasoner:** extract validated Parameter defaults/ranges, env_mapping data. Extract DERIVES_FROM (parameter → postulate) provenance. Flag invalid formulations.
  - **After Builder:** extract Model entity (class_name, formulation_id), TestResult entity. Extract IMPLEMENTS relation. Store code patterns as procedural memories.
- Output: structured `ExtractionResult` dataclass containing `nodes: list[NodeSpec]`, `relations: list[RelationSpec]`, `facts: list[str]` (plain-text memory facts)
- `NodeSpec`: label, properties dict, natural_key (for dedup)
- `RelationSpec`: from_label, from_key, to_label, to_key, rel_type, properties dict

### R2: Knowledge Graph Population
- Take `ExtractionResult.nodes` and `ExtractionResult.relations`, write to Neo4j
- Node deduplication: before creating a node, check if one with the same natural_key exists. If exists: merge properties (new values override, but preserve provenance). If not: create.
- Relation deduplication: before creating a relation, check if same (from, to, type) exists for current run. If exists with same properties: skip. If exists with different properties: create new relation with updated `valid_from`, mark old with `valid_to`.
- Provenance metadata on all relations: `run_id`, `created_at`, `confidence` (from extraction), `valid_from=now`, `valid_to=None`
- Batch operations: collect all nodes/relations, execute in a single Neo4j transaction for atomicity

### R3: Embedding & Qdrant Indexing
- Take stage output text + extracted facts, prepare for indexing
- Chunking strategy:
  - Deep research reports: split by section headers (## Foundations, ## Postulates, etc.), each section is a chunk
  - Formulations: each formulation block is a chunk
  - Reasoner specs: the full JSON is one chunk (small enough)
  - Builder code: the full model file is one chunk, the test file is another
  - Extracted facts: each fact is its own chunk (short, atomic)
- For each chunk: embed via Voyage AI (`embed_texts`, input_type="document"), generate sparse representation
- Upsert to appropriate Qdrant collections: `artifacts_dense`/`artifacts_sparse` for pipeline artifacts, `memories_dense`/`memories_sparse` for extracted facts
- Payload: entity_id, namespace (inferred from stage), source_stage, run_id, importance (default 5.0, updated later), confidence (default 0.8), created_at, text_preview

### R4: Conflict Resolution & Importance Scoring
- **Importance scoring** (Haiku): for each extracted fact, rate importance 1-10. Prompt includes the fact text + the stage context. Batch all facts in a single LLM call to reduce cost.
- **Duplicate detection**: for each extracted fact, query Qdrant `memories_dense` for similar existing memories (cosine similarity > 0.85). Also query Neo4j for entities with matching natural keys.
- **Conflict classification** (Sonnet, only when duplicates found): given the existing memory + new fact, classify as:
  - `DUPLICATE` → discard new fact
  - `CORROBORATION` → increment existing memory's corroborations count, boost confidence
  - `ENRICHMENT` → merge: supersede old memory with enriched version combining both
  - `CONTRADICTION` → supersede old memory, set new as current, log the contradiction
- **Memory persistence**: create `Memory` rows in Postgres via `shared/memories.py` helpers. Set importance from Haiku scoring. Set initial confidence based on source stage (Researcher: 0.6, Formalizer: 0.7, Reasoner: 0.8, Builder: 0.9 — higher stages have validated more).

### R5: Memory Agent Orchestrator & Router Integration
- `MemoryAgent` class in `phase1-pablo/src/decisionlab/agents/memory_agent.py`
- Main method: `async run(stage: Stage, stage_output: str, run_id: str, run_context: dict) -> MemoryAgentResult`
- Flow: extract (R1) → [KG population (R2) + embedding (R3)] in parallel → conflict resolution (R4)
- `MemoryAgentResult` dataclass: nodes_created, relations_created, facts_stored, conflicts_resolved, duration_ms
- Router integration: after each stage handler completes and before the review stage, call `memory_agent.run()`. Add to the Router's stage transition logic (not a new Stage enum value — it's a post-hook, not a pipeline stage).
- The Memory Agent is optional — if knowledge infrastructure is unavailable (Neo4j/Qdrant not connected), skip with a warning log. No pipeline disruption.
- Emit WebSocket status updates: `agent_status: memory_agent working/done` for frontend awareness

## Acceptance Criteria
- [ ] AC1: After a DeepResearcher stage completes on "homeostatic regulation", the Memory Agent extracts: Paradigm("homeostatic-regulation"), Variables (energy, hunger, ghrelin, leptin), BrainRegion("hypothalamus"), Papers (with DOIs), Postulates, and writes them to Neo4j
- [ ] AC2: After a Formalizer stage, Equations and Parameters are extracted and linked to their parent Paradigm via USES_EQUATION and BELONGS_TO relations
- [ ] AC3: After a Reasoner stage, DERIVES_FROM provenance edges connect Parameters to their source Postulates
- [x] AC4: Running the same deep report through extraction twice does not create duplicate nodes — the second run detects existing entities and merges
- [x] AC5: When a new fact contradicts an existing memory (e.g., different parameter default for same variable), Sonnet classifies it as CONTRADICTION and the old memory is superseded
- [x] AC6: When a new fact corroborates an existing memory, the existing memory's corroborations count increases and confidence rises
- [x] AC7: Importance scoring produces reasonable values: "ghrelin modulates hunger" scores higher than "the grid is 10x10"
- [x] AC8: All extracted facts are embedded and searchable in Qdrant within 2 seconds of Memory Agent completion
- [ ] AC9: Pipeline runs normally when Neo4j/Qdrant are unavailable — Memory Agent logs warning and skips
- [ ] AC10: WebSocket clients receive memory_agent status updates during pipeline execution

## Technical Notes
- Follow existing agent patterns: the Memory Agent is NOT an agentic-loop agent (no tool_use cycle). It's a deterministic pipeline: extract → populate → embed → resolve. LLM calls are direct (not through `runtime/loop.py`).
- Extraction prompts should be in a separate `prompts/` module or constants, not inline strings
- Use `asyncio.gather` for parallel KG population + embedding (same pattern as Formalizer/Reasoner parallelism)
- Conflict resolution Sonnet calls are the expensive path — only triggered when duplicates are detected (expected: <10% of facts on a typical run)

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Post-hook vs new Stage | Post-hook | Memory extraction is infrastructure, not a user-facing pipeline stage. No human review needed. |
| Deterministic pipeline vs agentic loop | Deterministic | Extraction is formulaic — no need for tool_use autonomy. Cheaper, faster, more predictable. |
| Stage-specific prompts vs generic | Stage-specific | Each stage produces radically different output (markdown vs LaTeX vs JSON vs Python). One prompt can't handle all. |
| Default confidence by stage | Researcher:0.6, Formalizer:0.7, Reasoner:0.8, Builder:0.9 | Later stages have undergone more validation. Research is raw web data; Builder output has passed tests. |
| Similarity threshold for dedup | 0.85 cosine | Conservative — avoids false positives. Can be tuned later. |
