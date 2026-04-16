# Knowledge Backbone — General Specification

> Status: current | Created: 2026-04-14 | Last updated: 2026-04-14

## Overview

A persistent knowledge layer for the DecisionLab pipeline (Phase 1) that replaces the current ephemeral file-cascade with a structured, queryable, cross-run memory system. Built on a 3-layered RAG architecture (Knowledge Graph + Dense Vectors + Sparse/Lexical) with a dedicated Memory Agent that curates knowledge after every pipeline stage, and Corrective RAG that validates retrieval quality before context injection.

The system targets researchers who run the pipeline repeatedly on related topics (e.g., food intake → addiction → reward learning). Each run enriches a shared knowledge base, so the 10th experiment produces substantially better results than the 1st — the lab gets smarter over time.

## Core Features

- **Knowledge Graph (Neo4j):** Structured entities (paradigms, variables, equations, brain regions, authors, papers, formulations, parameters) connected by typed relations (supports, contradicts, extends, measures, modulates, cites, implements). HippoRAG-style Personalized PageRank for multi-hop retrieval.
- **Dense Vector Store (Qdrant):** Voyage AI embeddings of pipeline artifacts at multiple granularities — chunk-level text, full documents, and paradigm-level summaries (natural RAPTOR-style hierarchy from existing pipeline outputs).
- **Sparse/Lexical Index (Qdrant sparse vectors):** BM25-equivalent full-text search over all artifacts. Catches exact matches (variable names, DOIs, author names, equation symbols) that dense retrieval misses.
- **3-Layer Retrieval + Fusion:** All three retrieval channels run in parallel. Results fused via Reciprocal Rank Fusion (RRF, k=60). Fused results reranked by Voyage AI reranker. Top-k injected into agent context.
- **Corrective RAG (CRAG):** After reranking, a Haiku evaluator classifies each result as CORRECT/AMBIGUOUS/INCORRECT. If all INCORRECT → fallback to fresh web search. If AMBIGUOUS → combine stored + fresh. Prevents stale or irrelevant memories from polluting generation.
- **Memory Agent:** Dedicated agent (Haiku for extraction/scoring, Sonnet for conflict resolution) that runs after every pipeline stage. Extracts entities, relations, facts, and provenance edges. Performs mem0-style deduplication and LLM-based conflict resolution. Scores importance (1-10 scale, Generative Agents pattern).
- **Cross-Run Persistence:** Immutable memories with temporal validity (Zep pattern: `valid_from`/`valid_to`, supersession pointers). Knowledge accumulates across pipeline runs. Consolidation runs after each completed run.
- **Provenance Tracking:** Every KG node/edge carries: source paper (title, authors, year, DOI, citation count), pipeline stage that produced it, run_id, confidence score, and the postulate-to-parameter derivation chain.
- **Memory Namespaces:** Five scoped collections — `paradigm/` (scientific facts), `formulation/` (math patterns), `model/` (code patterns, parameter ranges, test outcomes), `simulation/` (Phase 2 observations), `meta/` (pipeline strategy reflections).
- **Confidence Evolution:** Memories have confidence scores that evolve: corroboration from independent sources increases confidence, contradictions decrease it, time decay applies, and access frequency provides a usage signal.

## Out of Scope

- **Frontend visualization** of the knowledge graph (separate future phase)
- **Phase 2 agent memory** — Phase 2 agents (Tracker, Analyst, Reporter) do not write to the knowledge system in this scope; they may read from it via retrieval tools
- **Real-time knowledge updates during a stage** — the Memory Agent runs between stages, not within a stage's agentic loop
- **Automatic paradigm discovery from the knowledge graph** — the Researcher still drives discovery via web search; the KG provides supplementary context
- **Multi-user/multi-tenant isolation** — single knowledge base per deployment

## Data Model

### Knowledge Graph (Neo4j)

**Nodes:**

| Label | Key Properties | Example |
|-------|---------------|---------|
| `Paradigm` | name, slug, description | "Homeostatic Regulation" |
| `Variable` | name, type (state/parameter/input/output), range, unit | "energy_level", state, [0,100], "arbitrary units" |
| `Equation` | latex, plaintext, type (ODE/algebraic/probabilistic) | "D = phi*(x-s)^2" |
| `BrainRegion` | name, system (homeostatic/hedonic/cognitive) | "Nucleus Accumbens", hedonic |
| `Author` | name, affiliation | "Berridge, Kent C." |
| `Paper` | title, year, doi, citation_count, venue | "Dissecting components of reward..." |
| `Postulate` | id, statement, falsifiable | "P3: Dopamine mediates wanting, not liking" |
| `Formulation` | id, name, type, description | "T01-P01-F01", "Drive-Reduction RL" |
| `Parameter` | name, default_value, source, range | "learning_rate", 0.1, "Keramati 2011" |
| `Model` | formulation_id, class_name, s3_key, passed, failure_reason | "T01-P01-F01", "HomeostaticDriveReductionRL", true, null |

**Relations:**

| Type | From → To | Properties |
|------|-----------|------------|
| `SUPPORTS` | Paper → Postulate | confidence, quote |
| `CONTRADICTS` | Paper → Postulate | confidence, quote |
| `EXTENDS` | Paradigm → Paradigm | description |
| `MEASURES` | Variable → BrainRegion | mechanism |
| `MODULATES` | Variable → Variable | direction (positive/negative), equation_ref |
| `AUTHORED` | Author → Paper | |
| `DERIVES_FROM` | Parameter → Postulate | derivation_chain |
| `IMPLEMENTS` | Model → Formulation | |
| `USES_EQUATION` | Formulation → Equation | |
| `BELONGS_TO` | Postulate → Paradigm | |
| `CITES` | Paper → Paper | |

All relations carry temporal metadata: `created_at`, `run_id`, `confidence`, `valid_from`, `valid_to`, `superseded_by`.

### Memory Store (Postgres — extends existing `shared` schema)

```
Table: memories
  id: UUID PK
  content: text
  namespace: enum (paradigm, formulation, model, simulation, meta)
  memory_type: enum (episodic, semantic, procedural, reflection)
  source_stage: str              -- researcher, formalizer, reasoner, builder, memory_agent
  run_id: UUID FK → runs
  created_at: timestamp
  updated_at: timestamp
  last_accessed_at: timestamp
  access_count: int default 0
  importance: float              -- 1-10 scale
  confidence: float              -- 0-1 scale
  corroborations: int default 0
  contradictions: int default 0
  valid_from: timestamp
  valid_to: timestamp nullable   -- null = currently valid
  superseded_by: UUID nullable FK → memories
  metadata: jsonb                -- source_urls, evidence pointers, etc.
```

Embeddings stored in Qdrant (not Postgres) — the memories table holds the structured metadata; Qdrant holds the vectors with `memory_id` as payload.

### Vector Collections (Qdrant)

| Collection | Content | Embedding Model | Dimensionality |
|------------|---------|----------------|----------------|
| `artifacts_dense` | Pipeline artifact chunks (deep reports, formulations, specs, code) | Voyage AI `voyage-3` | 1024 |
| `artifacts_sparse` | Same chunks, sparse representation | Qdrant built-in BM25 | sparse |
| `memories_dense` | Extracted memory facts | Voyage AI `voyage-3` | 1024 |
| `memories_sparse` | Same facts, sparse representation | Qdrant built-in BM25 | sparse |

## Integrations

- **Neo4j** — knowledge graph storage, Cypher queries, community detection
- **Qdrant** — dense + sparse vector storage, ANN search, filtering
- **Voyage AI** — `voyage-3` embeddings, `rerank-2` reranker
- **Anthropic** — Haiku (extraction, importance scoring, CRAG evaluation), Sonnet (conflict resolution)
- **Existing infrastructure** — Postgres (shared schema), MinIO/S3 (artifact storage), pipeline Router

## User Flows

### Flow 1: First Pipeline Run (Cold Start)

1. User starts pipeline with problem description "food intake behavior"
2. Researcher runs, produces deep reports → **Memory Agent extracts** entities (paradigms, variables, brain regions), relations (modulates, measures), provenance (papers → postulates) → writes to Neo4j + Qdrant
3. Formalizer runs (with retrieval: queries KG for related formulations from past runs — none found on cold start) → Memory Agent extracts formulation patterns, equation entities, parameter sources
4. Reasoner runs (with retrieval: queries for similar specs, parameter ranges) → Memory Agent extracts validated specs, env mappings, validation outcomes
5. Builder runs (with retrieval: queries for working code patterns, test strategies) → Memory Agent extracts model patterns, test outcomes, failure modes
6. Pipeline completes → **Consolidation** runs: cluster related memories, generate reflections, prune duplicates

### Flow 2: Subsequent Run on Related Topic (Warm Start)

1. User starts pipeline with "addiction and reward learning"
2. Researcher runs — **retrieval injects** relevant paradigm knowledge from run 1 (hedonic system, dopamine pathways, Berridge's work already in KG). Researcher skips redundant searches, focuses on novel aspects.
3. Formalizer runs — **retrieval surfaces** formulation patterns that worked for reward-related paradigms in run 1. Formalizer builds on proven mathematical structures.
4. Same pattern continues through Reasoner and Builder — each benefits from accumulated knowledge
5. Memory Agent detects cross-run connections: "incentive salience" from run 1 relates to "addiction reward" in run 2 → creates `EXTENDS` edges in KG

### Flow 3: CRAG Correction

1. Builder queries memories for "Q-learning convergence patterns"
2. Retrieval returns 5 results, reranker scores them
3. CRAG evaluator (Haiku) classifies: 2 CORRECT, 1 AMBIGUOUS, 2 INCORRECT
4. INCORRECT results discarded. AMBIGUOUS result kept but supplemented with fresh web search for "Q-learning convergence in grid environments"
5. Combined context (2 CORRECT memories + AMBIGUOUS memory + web results) injected into Builder's prompt

## Constraints & Non-Functional Requirements

- **Latency:** 3-layer retrieval + RRF + reranking + CRAG must complete within ~2 seconds. Acceptable because LLM generation (the next step) takes 5-30 seconds.
- **Storage:** Neo4j and Qdrant run as Docker containers alongside existing MinIO and Postgres. Docker Compose extended.
- **Cost:** Memory Agent runs Haiku (~$0.001/stage) + occasional Sonnet for conflicts (~$0.01/conflict). Voyage AI embeddings ~$0.0001/1K tokens. Reranking ~$0.0001/query. Total overhead per pipeline run: <$0.10.
- **Consistency:** Memories are written after stage completion (not during). No concurrent write conflicts within a single pipeline run. Cross-run conflicts handled by the Memory Agent's conflict resolution.
- **Backward compatibility:** Existing pipeline stages (Researcher, Formalizer, Reasoner, Builder) gain new retrieval tools but their core behavior is unchanged. Runs without knowledge infrastructure should still work (graceful degradation — retrieval tools return empty results).

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Neo4j over NetworkX | Neo4j | User preference for robust infra; Cypher queries, temporal edges, community detection built-in |
| Qdrant over pgvector | Qdrant | Native sparse+dense support in single system; better ANN performance; user preference |
| Voyage AI over local models | Voyage AI | Best code+science embeddings; reranker included; single provider |
| Memory Agent over inline extraction | Dedicated agent | Clean separation of concerns; doesn't slow down pipeline stages; can use different models (Haiku for cheap extraction) |
| Immutable memories (Zep pattern) | Supersession, not mutation | Research context demands full history; "how did understanding evolve?" is a valid query |
| CRAG over threshold-only | Corrective RAG with web fallback | Prevents stale memories from degrading output; web fallback catches knowledge gaps |
| RRF over learned fusion | Reciprocal Rank Fusion (k=60) | No training data needed; proven effective; 10 lines of code |
| Haiku + Sonnet split | Haiku for extraction, Sonnet for conflicts | Cost optimization: extraction is formulaic (Haiku sufficient), conflict resolution needs reasoning (Sonnet) |
| 5 namespaces | paradigm, formulation, model, simulation, meta | Maps to pipeline stages and research concerns; prevents cross-contamination in retrieval |
