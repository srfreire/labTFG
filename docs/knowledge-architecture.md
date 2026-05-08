# Knowledge Backbone Architecture

## What this is

A persistent memory system for a multi-agent research pipeline. The pipeline reads scientific literature and generates decision-making models. Without this system, every run starts from zero. With it, knowledge accumulates across runs — run 10 is smarter than run 1.

## The problem

The pipeline has 4 agents (Researcher, Formalizer, Reasoner, Builder) that run sequentially. Each produces artifacts: reports, formulations, specs, code. Those artifacts are stored in S3 but never structured, never searchable, never reusable. If you run the pipeline on "food intake" and then on "addiction", the second run has no idea the first already mapped dopamine pathways, reward circuits, and homeostatic models.

## The solution at a glance

Three things happen:

1. **After each stage**, a Memory Agent reads the output, extracts structured knowledge, and stores it in three places (Neo4j, Qdrant, Postgres).
2. **During each stage**, agents can call a `retrieve_knowledge` tool that searches all stored knowledge, validates it, and injects relevant context.
3. **After each completed run**, a consolidation step clusters related memories, generates higher-level reflections, decays old knowledge, and prunes what's no longer useful.

---

## Storage layer

### Neo4j — Knowledge Graph

Stores entities and their relationships as a graph.

**10 node types:**

| Node | What it represents | Example |
|------|-------------------|---------|
| Paradigm | A scientific paradigm | "Homeostatic Regulation" |
| Variable | A measurable quantity | "energy_level", state, [0,100] |
| Equation | A mathematical relationship | "D = phi*(x-s)^2" |
| BrainRegion | A neural structure | "Nucleus Accumbens", hedonic system |
| Author | A researcher | "Berridge, Kent C." |
| Paper | A publication | "Dissecting components of reward...", 2007 |
| Postulate | A falsifiable claim | "Dopamine mediates wanting, not liking" |
| Formulation | A mathematical model design | "Drive-Reduction RL" |
| Parameter | A model parameter | "learning_rate", 0.1, from Keramati 2011 |
| Model | Generated code + test outcome | "HomeostaticDriveReductionRL", passed: true |

**11 relation types:**

| Relation | From → To | What it means |
|----------|-----------|--------------|
| SUPPORTS | Paper → Postulate | Paper provides evidence for a claim |
| CONTRADICTS | Paper → Postulate | Paper provides evidence against a claim |
| EXTENDS | Paradigm → Paradigm | One paradigm builds on another |
| MEASURES | Variable → BrainRegion | A variable quantifies activity in a region |
| MODULATES | Variable → Variable | One variable influences another |
| AUTHORED | Author → Paper | Who wrote what |
| DERIVES_FROM | Parameter → Postulate | How a parameter value was justified |
| IMPLEMENTS | Model → Formulation | Code that realizes a design |
| USES_EQUATION | Formulation → Equation | Mathematical basis of a formulation |
| BELONGS_TO | Postulate → Paradigm | Which paradigm a claim lives under |
| CITES | Paper → Paper | Citation link |

**Temporal metadata on every relation:**

Every relation carries `created_at`, `valid_from`, `valid_to`, `run_id`, and `confidence`. When new information supersedes old information, the old relation gets `valid_to = now()` and a new one is created. Nothing is deleted — the full history is preserved.

**Node upsert pattern:**

Nodes use Cypher MERGE — if the same entity appears in multiple runs, it merges rather than duplicates. The node accumulates `run_ids` so you can trace which runs contributed to it.

```cypher
MERGE (n:Paradigm {slug: $slug})
ON CREATE SET n += $create_props
ON MATCH SET n += $update_props, n.run_ids = coalesce(n.run_ids, []) + $run_id
```

### Qdrant — Vector Store

Stores embeddings for similarity search. Four collections:

| Collection | Content | Vector type | Dimensions |
|-----------|---------|-------------|-----------|
| artifacts_dense | Pipeline artifact chunks (reports, formulations, specs, code) | Dense (Voyage AI voyage-4-large) | 1024 |
| artifacts_sparse | Same chunks, sparse representation | Sparse (Qdrant native BM25, `modifier=IDF`) | variable |
| memories_dense | Extracted facts from the Memory Agent | Dense (Voyage AI voyage-4-large) | 1024 |
| memories_sparse | Same facts, sparse representation | Sparse (Qdrant native BM25, `modifier=IDF`) | variable |

**Why both dense and sparse?**

Dense vectors capture semantic meaning ("Q-learning" and "reinforcement learning" are close in vector space). Sparse vectors capture exact lexical matches ("Berridge" matches "Berridge", not "reward researcher"). Running both in parallel and fusing results gives the best of both.

**Native BM25 over a custom tokenizer.** Sparse collections use Qdrant's built-in BM25 (`Document(text=..., model="Qdrant/bm25")`) with `modifier=Modifier.IDF` on the collection. FastEmbed tokenizes and stems client-side; Qdrant applies IDF weighting, TF saturation, and document-length normalization server-side. We send raw text — no hashing, no manual stopword lists.

**Payload on every point:**

Each vector carries metadata: `entity_id`, `namespace`, `source_stage`, `run_id`, `importance`, `confidence`, `created_at`, `text_preview`.

### Postgres — Memory Lifecycle

The `memories` table tracks the lifecycle of every extracted fact:

| Column | Purpose |
|--------|---------|
| id | UUID primary key |
| content | The fact text |
| namespace | paradigm, formulation, model, simulation, or meta |
| memory_type | episodic, semantic, procedural, or reflection |
| source_stage | Which agent produced it (researcher, formalizer, reasoner, builder) |
| run_id | Which pipeline run |
| importance | 1-10 scale, scored by Haiku |
| confidence | 0-1 scale, evolves over time |
| corroborations | How many independent sources confirmed this |
| contradictions | How many sources disagreed |
| access_count | How many times retrieval used this memory |
| last_accessed_at | When retrieval last used it |
| valid_from | When this memory became valid |
| valid_to | When it was superseded (null = still valid) |
| superseded_by | UUID of the memory that replaced this one |
| metadata | JSONB blob for source URLs, evidence pointers, etc. |

**Why Postgres and not just Qdrant?**

Qdrant is a vector store — it finds similar content. Postgres handles the relational queries that Qdrant can't: "give me all paradigm memories with confidence > 0.8 from the last 3 runs that haven't been superseded." Confidence scores, temporal validity, supersession chains, namespace filtering, access tracking — all relational concerns.

### MinIO/S3 — Artifact Storage

Stores the raw files the pipeline produces: deep reports, formulations, reasoner specs, builder code, PDFs, charts. The Memory Agent reads from MinIO to extract knowledge. MinIO is the source material; the other three stores hold the processed knowledge derived from it.

---

## Memory Agent

A deterministic 3-step pipeline that runs after each stage completes. Not an agentic loop — no tool use, no multi-turn conversation. Just extract → write → resolve.

### Step 1: Extract

Model is tiered per stage: judgment-heavy stages on Sonnet 4.6
(`knowledge_structured_model`), mechanical stages on Haiku 4.5
(`knowledge_fast_model`). All four route through `call_structured`
(forced tool-use, max 32768 tokens).

| Stage | What gets extracted | Model |
|-------|---------------------|-------|
| Researcher | Paradigms, Authors, Papers, BrainRegions, Variables, Postulates + relations (BELONGS_TO, AUTHORED, SUPPORTS, MEASURES) | Sonnet 4.6 |
| Formalizer | Equations, Variables, Parameters, Formulations + relations (USES_EQUATION, MODULATES) | Haiku 4.5 |
| Reasoner | Parameters, Formulations + relations (DERIVES_FROM) | Sonnet 4.6 |
| Builder | Models (incl. `passed` + `failure_reason` test props) + relations (IMPLEMENTS) | Haiku 4.5 |

Output is structured JSON: `{"nodes": [...], "relations": [...], "facts": [...]}`. Facts are plain-text statements that don't fit neatly into the graph schema — things like "Q-learning converges faster with low learning rates in sparse reward environments."

### Step 2: Parallel write

Two operations run simultaneously via `asyncio.gather`:

1. **Neo4j**: MERGE nodes (idempotent upsert), check existing relations for supersession, create new relations with temporal metadata. All wrapped in a single write transaction.
2. **Qdrant**: Chunk the stage output, embed chunks with Voyage AI, upsert dense + sparse vectors into the appropriate collections.

### Step 3: Conflict resolution

For each extracted fact:

1. **Importance scoring** (Haiku via `knowledge_fast_model`, all facts in one batch call): scores each fact 1-10. Scoring guide: 1-3 trivial, 4-5 contextual, 6-7 informative, 8-10 fundamental.

2. **Duplicate detection**: embed the fact, search `memories_dense` for similar existing memories (threshold > 0.85 similarity, different run_id).

3. **Conflict classification** (Sonnet via `knowledge_structured_model`, only called when duplicates found): takes the existing memory + new fact and classifies the relationship:
   - `DUPLICATE` — same information, skip
   - `CORROBORATION` — independent confirmation, boost confidence +0.05
   - `ENRICHMENT` — new fact adds to existing knowledge, supersede old with merged content
   - `CONTRADICTION` — new fact disagrees, reduce confidence -0.10 on old, supersede, create a meta-memory recording the contradiction

4. **Store**: new facts that don't match anything existing are stored as new memories with stage-based initial confidence (researcher=0.6, formalizer=0.7, reasoner=0.8, builder=0.9).

---

## 3-Layer Retrieval

When an agent calls `retrieve_knowledge(query)`, three retrieval channels run in parallel:

### Layer 1: Knowledge Graph traversal

1. Haiku extracts named entities from the query (e.g., "dopamine", "reward learning")
2. Entity linking: first exact case-insensitive match against Neo4j nodes, then fuzzy embedding similarity (threshold 0.75) for entities that don't match exactly
3. For each linked entity: 2-hop BFS traversal with exponential decay (score = confidence * 0.85^hops). Multiple paths to the same node keep the max score.
4. Results formatted as passages: `"Paradigm (name: Homeostatic Regulation, ...) [via EXTENDS -> BELONGS_TO]"`

This is a PPR-inspired local traversal, not full iterative PageRank. At the graph sizes we work with (hundreds to low thousands of nodes), local 2-hop traversal gives equivalent results without convergence overhead.

### Layer 2: Dense vector search

1. Embed the query with Voyage AI `voyage-4-lite` (asymmetric: `input_type="query"`)
2. Search `artifacts_dense` and `memories_dense` in parallel
3. Merge and sort by score

### Layer 3: Sparse vector search

1. Send the raw query to Qdrant as `Document(text=..., model="Qdrant/bm25")`; FastEmbed tokenizes client-side, Qdrant scores with BM25 (IDF server-side)
2. Search `artifacts_sparse` and `memories_sparse` in parallel
3. Normalize scores to 0-1

### Fusion

**RRF (Reciprocal Rank Fusion, k=60, top 30):**

Each result gets score `1/(k + rank)` within its list. Same document appearing in multiple lists gets scores summed. Top 30 kept.

**Reranking:**

Fused results are reranked by ZeroEntropy `zerank-2`. Results below threshold 0.3 are filtered out. Top 10 kept.

### CRAG evaluation

Haiku classifies each reranked result as CORRECT, AMBIGUOUS, or INCORRECT for the given query.

| Situation | Action |
|-----------|--------|
| All CORRECT | Pass through as-is |
| Mix of CORRECT and INCORRECT, no AMBIGUOUS | Keep only CORRECT |
| Any AMBIGUOUS | Keep CORRECT + AMBIGUOUS, fetch web results via DuckDuckGo, merge + rerank combined set |
| All INCORRECT | Full web fallback — DuckDuckGo search + rerank, discard stored results |

### Post-processing

Before returning to the agent:

1. **Recency weighting**: `final_score = score * (0.995^days_old) * confidence_factor`
2. **Temporal filtering**: if `as_of` parameter is set, only keep results where `created_at <= as_of AND (valid_to IS NULL OR valid_to > as_of)`
3. **Memory access tracking**: each accessed memory gets `access_count += 1` and `confidence += 0.02` (fire-and-forget, non-blocking)

---

## Confidence evolution

Memories have a confidence score that changes over their lifetime:

| Event | Effect |
|-------|--------|
| Creation (researcher stage) | 0.6 |
| Creation (formalizer stage) | 0.7 |
| Creation (reasoner stage) | 0.8 |
| Creation (builder stage) | 0.9 |
| Corroboration (independent source confirms) | +0.05, capped at 1.0 |
| Contradiction (source disagrees) | -0.10, floored at 0.1 |
| Accessed via retrieval | +0.02, capped at 1.0 |
| Time decay (not accessed in 30+ days) | confidence *= 0.95 per 30-day period, floored at 0.1 |

Reflections (generated during consolidation) are exempt from time decay.

---

## Post-run consolidation

Runs after the pipeline completes. Four steps:

### 1. Cluster

Load all valid memories from this run. Embed them all with Voyage AI. Compute pairwise cosine similarity matrix (NumPy). Single-linkage clustering at threshold 0.80. Returns clusters of 2+ related memories.

### 2. Reflect

For clusters of 3+ memories, Haiku generates 1-2 higher-level insights. Example: if 4 memories all mention dopamine's role in different reward contexts, the reflection might be "Dopamine consistently appears as a modulator across reward paradigms, suggesting it's a general-purpose reward signal rather than paradigm-specific."

Reflections are stored as `meta/reflection` memories with importance=8.0 and confidence=0.7.

Cross-run comparison: if a similar reflection (>0.85 similarity) exists from a different run, check if it contradicts or corroborates. Corroboration boosts the existing reflection's confidence.

### 3. Time decay

Apply `confidence *= 0.95^(periods)` to all memories not accessed in 30+ days. Sync updated confidences to Qdrant payloads so retrieval filtering stays accurate.

### 4. Prune

Soft-delete (set `valid_to = now()`) memories where:
- confidence < 0.2
- access_count == 0
- older than 90 days
- not already superseded

Nothing is hard-deleted. Pruned memories are still queryable via temporal queries (`as_of` parameter).

---

## Pipeline integration

### How agents get the retrieval tool

The Router checks if knowledge infrastructure is available (`shared.kg`, `shared.vectors`, `shared.embeddings`). If all three exist, it creates a `retrieve_knowledge` tool closure and passes it to each agent. If any are missing, agents run without the tool — no crash, no error, just no knowledge augmentation.

The tool schema:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| query | string | yes | What to search for |
| namespace | enum | no | Filter to paradigm/formulation/model/simulation/meta |
| top_k | int | no | Number of results (default 5) |
| as_of | ISO8601 string | no | Temporal query — only return knowledge valid at this point in time |

### How the Memory Agent hooks into the Router

After each stage advances successfully, the Router checks if a Memory Agent is available. If so, it:

1. Collects the stage output from S3 (reports, formulations, specs, or code depending on stage)
2. Calls `memory_agent.run(stage, output, run_id)`
3. Logs the result but never blocks the pipeline on failure

After the final stage (DONE), the Router calls `_run_consolidation()`.

### Graceful degradation

Everything degrades gracefully. If Neo4j is down, the KG retrieval layer returns empty results but dense + sparse still work. If Qdrant is down, vector search returns empty but KG traversal still works. If everything is down, agents run exactly as they did before the knowledge system existed. The Memory Agent catches all exceptions and logs them — it never crashes the pipeline.

---

## LLM usage summary

Extraction is tiered per stage. Judgment-heavy stages run on Sonnet 4.6
(`knowledge_structured_model`); mechanical stages run on Haiku 4.5
(`knowledge_fast_model`). Slot defaults are env-overridable via
`DECISIONLAB_KNOWLEDGE_FAST_MODEL` and `DECISIONLAB_KNOWLEDGE_STRUCTURED_MODEL`.

| Component | Model | Purpose | Cost per call |
|-----------|-------|---------|--------------|
| Extraction — Researcher | Sonnet 4.6 (`knowledge_structured_model`) | Filter slugs, scope `paradigm_slug` across nested entities | ~$0.01 |
| Extraction — Formalizer | Haiku 4.5 (`knowledge_fast_model`) | Equations / Variables / Parameters / Formulations from rigid tables | ~$0.001 |
| Extraction — Reasoner | Sonnet 4.6 (`knowledge_structured_model`) | Trace `DERIVES_FROM` chains via JSON `rules` array | ~$0.01 |
| Extraction — Builder | Haiku 4.5 (`knowledge_fast_model`) | Extract one Model node + IMPLEMENTS from generated `.py` | ~$0.001 |
| Importance scoring | Haiku 4.5 (`knowledge_fast_model`) | Score facts 1-10 | ~$0.001 |
| Conflict resolution | Sonnet 4.6 (`knowledge_structured_model`) | DUPLICATE / CORROBORATION / ENRICHMENT / CONTRADICTION + merge | ~$0.01 |
| CRAG evaluation | Haiku 4.5 (`knowledge_fast_model`) | Classify retrieval results | ~$0.001 |
| NER for retrieval | Haiku 4.5 (`knowledge_fast_model`) | Extract entities from queries | ~$0.0005 |
| Reflection generation | Sonnet 4.6 (`knowledge_structured_model`) | Higher-level insights from clusters | ~$0.01 |
| Embedding | Voyage AI voyage-4-large | Document embeddings (1024-dim) | ~$0.0001/1K tokens |
| Query embedding | Voyage AI voyage-4-lite | Query embeddings (asymmetric) | ~$0.0001/1K tokens |
| Reranking | ZeroEntropy zerank-2 | Rerank fused results | ~$0.0001/query |

Total overhead per pipeline run: < $0.10.

---

## Key design decisions

| Decision | Choice | Why |
|----------|--------|-----|
| 3 stores (Neo4j + Qdrant + Postgres) | Each does something the others can't | Neo4j = graph traversal, Qdrant = vector search (dense+sparse), Postgres = relational lifecycle queries |
| Immutable memories | Supersession, not mutation | Research context demands full history — "how did understanding evolve?" is a valid query |
| CRAG over threshold-only | Corrective RAG with web fallback | Prevents stale memories from degrading output |
| RRF over learned fusion | Reciprocal Rank Fusion (k=60) | No training data needed, proven effective, trivial to implement |
| Tiered extraction model (Haiku/Sonnet per stage) | Cost optimization | Mechanical stages (Formalizer, Builder) hit Haiku; judgment-heavy stages (Researcher, Reasoner) and conflict resolution hit Sonnet |
| Memory Agent between stages, not during | Clean separation | Doesn't slow down agent loops, can use different models |
| 5 namespaces | paradigm, formulation, model, simulation, meta | Maps to pipeline stages, prevents cross-contamination in retrieval |
| 2-hop BFS, not full PPR | Local approximation | Graph is small enough that 2-hop gives equivalent results without convergence cost |
