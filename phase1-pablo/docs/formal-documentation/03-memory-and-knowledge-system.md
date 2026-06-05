# Memory and Knowledge System

## Purpose

The memory system makes Phase 1 cumulative. Without it, each run starts from
zero. With it, accepted outputs become reusable knowledge for later runs.

The system is called a knowledge backbone because it combines:

- graph structure for scientific entities and relations
- dense and sparse retrieval for semantic and lexical search
- relational lifecycle metadata for confidence, validity and supersession
- corrective retrieval to avoid injecting irrelevant memories

## High-Level Flow

```text
Agent stage output
  -> human review accepts it
  -> Router enters MEMORY_* stage
  -> MemoryAgent
       -> extract structured nodes, relations, facts
       -> canonicalize new paradigm slugs
       -> write graph + index facts
       -> resolve duplicates/conflicts
  -> Post-run consolidation
```

The MemoryAgent is deterministic orchestration, not a free agentic loop. It uses
LLMs for structured extraction and judgment tasks, but the control flow is fixed.

## Why Memory Runs After Review

The system intentionally stores accepted output:

```text
raw LLM draft -> human review -> accepted artifact -> memory write
```

This avoids polluting the knowledge base with rejected formulations, invalid
specifications, or failed code variants. It also makes memory results easier to
explain in the thesis: memory is a curated record of the pipeline, not a log of
every intermediate thought.

## MemoryAgent Steps

```text
MemoryAgent.run(stage, output, run_id)
  |
  +-- 1. Extract
  |     structured nodes + relations + plain facts
  |
  +-- 1b. Canonicalize
  |      resolve __NEW__ paradigm proposals
  |
  +-- 2. Parallel write
  |      Neo4j graph write
  |      Qdrant dense/sparse fact indexing
  |
  +-- 2b. KG health pass
  |      repair readability / inferred relations
  |
  +-- 3. Resolve
        score importance
        detect duplicates
        classify conflicts
        persist lifecycle rows in Postgres
```

The output is a compact `MemoryAgentResult`: nodes created/merged, relations
created, facts stored, duplicates skipped, conflicts resolved, errors and timing.

## Extraction Model

Each accepted stage is converted into:

```python
ExtractionResult(
    nodes=[NodeSpec(...), ...],
    relations=[RelationSpec(...), ...],
    facts=["atomic memory fact", ...],
    stage="researcher|formalizer|reasoner|builder",
    run_id="..."
)
```

The extraction layer uses structured outputs with Pydantic validation. It does
not trust arbitrary JSON. Slug-bearing labels such as `Paradigm`, `Variable` and
`Postulate` are validated against canonical vocabulary plus the `__NEW__`
escape.

Stage model selection is tiered:

| Stage | Extraction character | Model slot |
| --- | --- | --- |
| researcher | judgment-heavy scientific extraction | knowledge structured |
| formalizer | more mechanical table/equation extraction | knowledge fast |
| reasoner | judgment-heavy derivation and mapping extraction | knowledge structured |
| builder | mechanical model/test extraction | knowledge fast |

This split keeps cost predictable while preserving stronger reasoning for
stages where entity relationships are more ambiguous.

## Canonical Slug Flow

Paradigm identity is one of the hardest problems. The system avoids uncontrolled
slug minting through a layered process:

```text
canonical-paradigms.json
  -> Classifier proposes umbrella
  -> Researcher list_known_slugs()
  -> structured output enum: known slugs + __NEW__
  -> if __NEW__:
       ANN search in Neo4j vector index
       Sonnet verify-merge gate
       merge existing or mint new slug
```

This prevents semantically related labels from fragmenting the graph. For
example, a run about temporal-difference learning should reuse a broad
reinforcement-learning umbrella when appropriate instead of minting a narrow
variant as a separate paradigm.

## Store Responsibilities

```text
                 +-----------------------+
                 | Accepted stage output |
                 +-----------+-----------+
                             |
       +---------------------+---------------------+
       |                     |                     |
       v                     v                     v
   Neo4j                 Qdrant                Postgres
 graph identity       similarity search       lifecycle truth
 entities/edges       dense + sparse facts    confidence/time
```

| Store | Responsibility |
| --- | --- |
| MinIO | Raw artifacts: reports, formulations, specs, code, traces, state. |
| Postgres | Runs, artifacts metadata, registered models, memory lifecycle, confidence, temporal validity. |
| Neo4j | Scientific graph topology: paradigms, papers, variables, postulates, formulations, models and typed relations. |
| Qdrant | Searchable memory facts in dense and sparse collections. |

Current Qdrant design uses two collections:

```text
memories_dense   -> Voyage dense embeddings
memories_sparse  -> native Qdrant BM25 sparse vectors
```

Older artifact collections were removed. Raw artifacts remain in MinIO and only
extracted facts enter Qdrant.

## Graph Model

Neo4j stores entity identity and relationships. Important labels include:

```text
Paradigm, Variable, Paper, Author, BrainRegion,
Postulate, Formulation, Parameter, Model, Reflection
```

Important relation types include:

```text
SUPPORTS, CONTRADICTS, EXTENDS, MEASURES, MODULATES,
AUTHORED, DERIVES_FROM, IMPLEMENTS, USES_EQUATION,
USES_VARIABLE, HAS_PARAMETER, GOVERNS, BELONGS_TO, CITES
```

Relations carry only graph identity and a `memory_id` link when they come from
Phase 1 memories. Temporal validity lives in Postgres. This avoids making Neo4j
both a graph database and a temporal lifecycle database.

## Postgres Memory Lifecycle

Phase 1 writes `pipeline_memories`. Each memory stores:

- content
- namespace
- memory type
- source stage
- run id
- importance
- confidence
- corroboration and contradiction counts
- access count
- validity interval
- supersession pointer

The lifecycle is:

```text
new fact
  -> no duplicate: create memory
  -> duplicate: skip
  -> corroboration: increase confidence
  -> enrichment: supersede old with merged content
  -> contradiction: lower old confidence, supersede, add meta-memory
```

Confidence changes are clamped:

```text
corroboration: +0.05
contradiction: -0.10
retrieval access: +0.02
time decay: * 0.95 per 30 days without access
floor/cap: 0.1 to 1.0
```

## Retrieval Tool

All pipeline agents can receive `retrieve_knowledge` when infrastructure is
available.

```text
Agent query
  -> query rewrite
  -> Qdrant dense retrieval
  -> Qdrant sparse retrieval
  -> optional Neo4j KG retrieval
  -> reciprocal rank fusion
  -> ZeroEntropy rerank
  -> optional CRAG grading / web supplement
  -> recency + confidence weighting
  -> optional temporal filtering
  -> formatted context
```

### Dense and Sparse Retrieval

Dense retrieval uses Voyage query embeddings and catches semantic similarity.
Sparse retrieval uses Qdrant's native BM25 and catches exact names, symbols,
authors, identifiers and technical terms.

The two channels are complementary:

```text
dense:  "temporal difference learning" ~= "reinforcement learning"
sparse: "Berridge" matches "Berridge" exactly
```

### Knowledge Graph Retrieval

KG retrieval has four steps:

```text
1. Haiku extracts named entities from the query
2. entities are linked by exact match or Neo4j vector index
3. local 2-hop traversal scores neighbors
4. nodes are formatted as retrieval passages
```

Traversal is intentionally local. It gives useful multi-hop context without the
cost of full graph algorithms on every query.

### Fusion and CRAG

Results from graph, dense and sparse channels are fused with Reciprocal Rank
Fusion. Fused results are reranked. If confidence is high enough, CRAG is
skipped to save latency. Otherwise, a fast model classifies results as correct,
ambiguous or incorrect:

```text
all correct             -> pass through
correct + incorrect     -> keep correct
ambiguous present       -> supplement with web
all incorrect           -> web fallback
grader unavailable      -> return reranked with warning marker
```

This prevents stale or irrelevant stored knowledge from silently shaping a new
run.

## Retrieval Use by Stage

| Stage | Retrieval usage |
| --- | --- |
| Researcher | Programmatically lists known paradigm slugs, then prompt requires at least one `retrieve_knowledge` call. |
| DeepResearcher | Supports retrieval when wired directly by Router review path. |
| Formalizer | Prompt asks for existing mathematical patterns and parameter sources. |
| Reasoner | Prompt asks for validated parameter ranges and environment mapping patterns. |
| Builder | Prompt asks for working code patterns, test strategies and pitfalls. |

The Researcher is the most strictly controlled because paradigm identity affects
the entire run.

## Post-Run Consolidation

After a completed run, the Router can trigger consolidation. Its role is to:

- cluster related memories
- generate higher-level reflections
- corroborate similar reflections across runs
- decay stale memories
- prune low-value memories

This is the difference between simple retrieval storage and a long-lived memory
system. The memory store is not append-only noise; it has lifecycle management.

## Design Tensions

| Tension | Current answer |
| --- | --- |
| Store everything vs store accepted output | Store accepted output after review. |
| Full graph temporal model vs relational temporal truth | Neo4j stores topology; Postgres stores time/confidence. |
| Fast retrieval vs robust correction | Skip CRAG on strong rerank scores; use CRAG when uncertain. |
| Avoid duplicates vs allow new paradigms | Canonical slugs plus `__NEW__` and verify-merge. |
| Raw artifacts vs searchable facts | Raw artifacts in MinIO; extracted facts in Qdrant. |

## Code Anchors

- MemoryAgent: `src/decisionlab/agents/memory_agent.py`
- Extraction: `src/decisionlab/knowledge/extraction.py`
- KG writing: `src/decisionlab/knowledge/kg_writer.py`
- Fact indexing: `src/decisionlab/knowledge/indexer.py`
- Conflict resolution: `src/decisionlab/knowledge/resolver.py`
- Retrieval tool: `src/decisionlab/knowledge/retrieval/tool.py`
- Vector retrieval: `src/decisionlab/knowledge/retrieval/vector_retrieval.py`
- KG retrieval: `src/decisionlab/knowledge/retrieval/kg_retrieval.py`
- Fusion: `src/decisionlab/knowledge/retrieval/fusion.py`
- CRAG: `src/decisionlab/knowledge/retrieval/crag.py`
- Memory tables: `../shared/shared/models.py`
- Memory helpers: `../shared/shared/pipeline_memories.py`

