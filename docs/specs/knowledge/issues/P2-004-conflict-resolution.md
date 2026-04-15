---
id: P2-004
title: Implement conflict resolution, importance scoring, and memory persistence
status: done
kind: strike
phase: 2
heat: resolution
priority: 3
blocked_by: [P2-001, P2-003]
created: 2026-04-14
updated: 2026-04-15
---

# P2-004: Implement conflict resolution, importance scoring, and memory persistence

## Objective
Score the importance of each extracted fact (Haiku), detect duplicates/contradictions against existing memories (Qdrant similarity search), resolve conflicts (Sonnet when contradictions detected), and persist final memories to Postgres.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/resolver.py`

- `async resolve_and_store(extraction: ExtractionResult, embedding_service: EmbeddingService, vector_store: VectorStore, db_session: AsyncSession, client: AsyncAnthropic) -> ResolutionResult`

- **Step 1: Importance scoring (Haiku, batch)**
  - Single Haiku call with all facts from `extraction.facts`
  - Prompt: "Rate the importance of each fact for a researcher studying decision-making paradigms. Score 1-10 where 1=trivial (grid dimensions, formatting) and 10=fundamental (core mechanism, key finding, validated parameter)."
  - Output: JSON list of `{"fact": str, "importance": int, "reasoning": str}`
  - If Haiku call fails: default all facts to importance 5.0

- **Step 2: Duplicate detection (Qdrant)**
  - For each fact, embed via `embedding_service.embed_query(fact)`
  - Search `memories_dense` with cosine similarity, limit=5
  - Threshold: similarity > 0.85 → candidate duplicate
  - Also search by exact run_id to skip self-matches from re-runs

- **Step 3: Conflict classification (Sonnet, only when duplicates found)**
  - For each fact with a candidate duplicate (similarity > 0.85):
    - Call Sonnet with: existing memory content + new fact + their source stages + timestamps
    - Prompt: "Classify this relationship: DUPLICATE (same information), CORROBORATION (independent confirmation), ENRICHMENT (new detail about same topic), or CONTRADICTION (conflicting information). Respond with JSON: {classification, reasoning, merged_content (for ENRICHMENT only)}"
    - Handle each classification:
      - `DUPLICATE`: discard new fact, do not create memory
      - `CORROBORATION`: call `update_confidence(existing_id, corroborate=True)`, do not create new memory
      - `ENRICHMENT`: call `supersede_memory(existing_id, merged_content)`, update Qdrant with new embedding
      - `CONTRADICTION`: call `supersede_memory(existing_id, new_fact)`, increment contradictions on old memory, log contradiction for audit

- **Step 4: Memory persistence (Postgres)**
  - For facts without duplicates (new knowledge): call `create_memory()` with:
    - content: fact text
    - namespace: inferred from stage (researcher→paradigm, formalizer→formulation, reasoner→formulation, builder→model)
    - memory_type: "semantic" for factual statements, "procedural" for code patterns, "episodic" for test outcomes
    - source_stage: from extraction.stage
    - run_id: from extraction.run_id
    - importance: from Haiku scoring
    - confidence: default by stage (researcher:0.6, formalizer:0.7, reasoner:0.8, builder:0.9)

- `ResolutionResult` dataclass:
  ```python
  @dataclass
  class ResolutionResult:
      memories_created: int
      duplicates_skipped: int
      corroborations: int
      enrichments: int
      contradictions: int
      sonnet_calls: int        # track expensive calls
      importance_scores: dict  # fact → score mapping for logging
  ```

## Acceptance Criteria
- [x] AC1: Importance scoring assigns "ghrelin modulates hunger via hypothalamic signaling" a score >= 7 and "the grid has resources" a score <= 4
- [x] AC2: A fact identical to an existing memory (similarity > 0.85) triggers Sonnet classification and is correctly classified as DUPLICATE — no new memory created
- [x] AC3: A fact that adds detail to an existing memory (e.g., "learning rate = 0.1" existing, "learning rate = 0.1, sourced from Keramati 2011" new) is classified as ENRICHMENT — old memory superseded, new memory created with merged content
- [x] AC4: A contradictory fact (e.g., "setpoint = 50" existing, "setpoint = 70 based on updated data" new) is classified as CONTRADICTION — old memory superseded with valid_to set, new memory created, contradictions counter incremented
- [x] AC5: Facts with no existing duplicates are stored directly with correct namespace, memory_type, importance, and confidence
- [x] AC6: Sonnet is only called when duplicates are detected (sonnet_calls == 0 when no duplicates found)
- [x] AC7: If Haiku importance scoring fails, all facts default to importance 5.0 and processing continues

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — new file
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — add importance scoring + conflict resolution prompts
- `phase1-pablo/src/decisionlab/knowledge/models.py` — add ResolutionResult dataclass

## Context
Phase spec: `docs/specs/knowledge/phase-2-memory-agent.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `resolution`
Depends on P2-001 (ExtractionResult format) and P2-003 (Qdrant must be populated to detect duplicates).
Uses `memories.py` helpers from P1-002, `EmbeddingService` from P1-004, `VectorStore` from P1-003.

## Completion Summary

**Commit:** `de6e135` — `feat[knowledge]: conflict resolution, importance scoring, memory persistence (P2-004)`

### What was built
- `resolver.py` with `resolve_and_store()` — 4-step pipeline: importance scoring (Haiku batch), duplicate detection (Qdrant cosine > 0.85), conflict classification (Sonnet per-duplicate), memory persistence (Postgres)
- `ResolutionResult` dataclass tracking memories_created, duplicates_skipped, corroborations, enrichments, contradictions, sonnet_calls, importance_scores
- Importance scoring and conflict classification prompts in `prompts.py`
- Graceful degradation: Haiku failure defaults importance to 5.0, Sonnet failure stores fact as new
- UUID type safety: string IDs converted to `uuid.UUID` for Postgres compatibility
- CONTRADICTION path: `update_confidence` called before `supersede_memory` so counters update on live row
- `merged_content: null` handling: falls back to fact text via `or` guard

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/resolver.py` — new: `resolve_and_store()`, `_score_importance()`, `_find_duplicates()`, `_classify_conflict()`
- `phase1-pablo/src/decisionlab/knowledge/models.py` — added `ResolutionResult` dataclass
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — added importance scoring + conflict classification prompts
- `phase1-pablo/src/decisionlab/knowledge/__init__.py` — exports `ResolutionResult`, `resolve_and_store`
- `phase1-pablo/tests/knowledge/test_resolver.py` — 20 tests covering all 7 ACs plus edge cases

### Decisions
- Renamed `_NAMESPACE_BY_STAGE` → `_STAGE_NAMESPACE` (etc.) to follow `_STAGE_*` naming convention from `indexer.py`
- Hoisted namespace/memory_type/confidence lookups out of per-fact loop (constant per invocation)
- Simplified `_find_duplicates` to list comprehension
- Added `exc_info=True` to warning logs for debuggability
