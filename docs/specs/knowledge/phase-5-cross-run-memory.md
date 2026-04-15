# Phase 5: Cross-Run Memory & Consolidation

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-15
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Enable persistent memory that improves across pipeline runs: cross-run retrieval scoping, confidence evolution (corroboration/contradiction tracking over time), post-run consolidation (clustering related memories, generating reflections, pruning stale knowledge), and temporal validity management.

## Requirements

### R1: Cross-Run Retrieval Scoping
- Retrieval queries search ALL runs by default (not just current run), but exclude current run_id to avoid self-retrieval.
- Results include `run_id` in metadata so the agent knows which run produced each result.
- Retrieval ranking incorporates recency: memories from recent runs score slightly higher than old ones.
- Recency scoring: `recency_boost = decay^days_since_creation` where decay = 0.995 (Generative Agents pattern). Applied as a multiplier on the final score after reranking.

### R2: Confidence Evolution
- When the Memory Agent detects a corroboration (same fact confirmed by independent run): increment `corroborations`, boost `confidence` by +0.05 (capped at 1.0).
- When a contradiction is detected: increment `contradictions`, decrease `confidence` by -0.10 (floored at 0.1).
- Time decay on confidence: memories not accessed in >30 days get `confidence *= 0.95` per 30-day period during consolidation.
- Access boost: each time a memory is retrieved and used (via `touch_memory`), confidence gets +0.02 (capped at 1.0). Frequently useful memories strengthen.

### R3: Post-Run Consolidation
- `async consolidate(db_session, kg, vector_store, embedding_service, client) -> ConsolidationResult`
- Runs after a pipeline run completes (called from Router after BUILD stage + Memory Agent)
- Steps:
  1. **Cluster related memories**: embed all memories from the completed run, cluster by cosine similarity (threshold > 0.80). Group into clusters of related facts.
  2. **Generate reflections**: for each cluster of >=3 memories, call Haiku to synthesize a higher-level insight (Generative Agents reflection pattern). Store as a new memory with `memory_type="reflection"`, `namespace="meta"`.
  3. **Detect cross-run patterns**: compare new reflections against existing reflections from past runs. If similar reflection already exists, corroborate it. If contradictory, flag for future review.
  4. **Apply time decay**: for all memories not accessed in >30 days, apply confidence decay.
  5. **Prune**: memories with `confidence < 0.2` AND `access_count == 0` AND `age > 90 days` → set `valid_to=now` (soft delete, not hard delete).

### R4: Temporal Validity Management
- All memories and KG relations use the immutable+supersession pattern:
  - Never mutate content. To update: create new, mark old with `valid_to=now` and `superseded_by=new_id`.
  - Retrieval filters to `valid_to IS NULL` by default (only current knowledge).
  - Historical queries can override this filter to see knowledge evolution.
- KG temporal queries:
  - "What did we know about ghrelin as of run X?" → filter relations by `valid_from <= run_date AND (valid_to IS NULL OR valid_to > run_date)`
  - Implemented as a Cypher query helper in `KnowledgeGraph`

## Acceptance Criteria
- [x] AC1: After 3 runs on related topics, retrieve_knowledge for run 4 returns results from all 3 prior runs with appropriate recency weighting (run 3 results score higher than run 1)
- [ ] AC2: A fact confirmed in 3 independent runs has confidence > 0.8 (starting from 0.6 + 3 corroboration boosts)
- [ ] AC3: A fact contradicted in a later run has decreased confidence and the new fact is the one retrieved (old one has valid_to set)
- [ ] AC4: Post-run consolidation generates at least 1 reflection memory from a cluster of related facts
- [ ] AC5: Memories older than 90 days with 0 access and confidence < 0.2 are pruned (valid_to set)
- [ ] AC6: Time decay reduces confidence of untouched memories by ~5% per 30-day period
- [ ] AC7: Frequently accessed memories (access_count > 10) maintain or increase confidence despite age

## Technical Notes
- Consolidation is computationally light — the most expensive part is the Haiku reflection calls (~1 per cluster of 3+ memories). Expect <10 clusters per run → <$0.01 total.
- Clustering: simple pairwise cosine similarity with single-linkage clustering. No need for DBSCAN/K-means — the memory count per run is small (~30-100 facts).
- The recency decay constant (0.995) means a 30-day-old memory retains ~86% of its recency score. A 90-day-old memory retains ~64%. A 365-day-old memory retains ~16%.
- Pruning is soft: `valid_to` is set, but the memory row and Qdrant vectors remain. Hard cleanup can be a future maintenance task.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Recency decay 0.995 | 0.995 per day | Balances freshness preference with long-term value. Old knowledge shouldn't disappear quickly. |
| Prune threshold | confidence < 0.2 AND access_count == 0 AND age > 90 days | Triple condition prevents aggressive pruning. Only truly useless memories are pruned. |
| Soft delete vs hard delete | Soft (valid_to set) | Research context — never destroy knowledge. Can always be recovered. |
| Consolidation timing | After pipeline run completes | Natural checkpoint. Don't consolidate mid-run (memories are still being created). |
