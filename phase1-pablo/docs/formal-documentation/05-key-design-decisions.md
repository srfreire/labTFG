# Key Design Decisions

This document records the main engineering decisions visible in the current
Phase 1 system. It is written for thesis use: concise rationale, tradeoffs, and
where the decision appears in code.

## 1. Separate Cognitive Stages

Decision:

```text
Researcher -> Formalizer -> Reasoner -> Builder
```

Rationale:

- research, mathematics, environment adaptation and code generation are
  different cognitive tasks
- each stage has a clear artifact boundary
- human review can intervene at the correct level
- later stages can be rerun without repeating earlier work

Tradeoff:

- more orchestration complexity
- more artifacts to manage
- more review gates

Why it is still worth it: a bad implementation, bad JSON spec and bad
scientific formulation require different fixes. One monolithic agent would make
that hard to diagnose.

## 2. Router as Explicit Stage Machine

Decision: use a Python Router with a finite set of stages instead of letting an
LLM decide the whole pipeline.

Rationale:

- deterministic continuation and resume
- clear human-in-the-loop points
- per-stage tracing and status
- memory writes can be placed after accepted output
- eval harness can stop after specific stages

Tradeoff:

- Router becomes a large central file
- adding stages requires explicit code changes

This is a good fit because the scientific generation is uncertain, but the
workflow itself is known.

## 3. Human Review Before Memory

Decision: store memory after review gates, not immediately after each agent
draft.

```text
agent output -> review -> MEMORY_* -> next stage
```

Rationale:

- prevents rejected outputs from entering the knowledge backbone
- keeps memory explainable as curated knowledge
- avoids teaching later agents from invalid formulations or failed builds

Tradeoff:

- rejected outputs are less available for failure analysis unless kept in raw
  artifacts/traces
- memory is delayed by one review step

## 4. Generated Models Use Duck Typing

Decision: generated models implement a small method contract instead of
subclassing a framework base class.

```python
decide(perception: dict) -> Action
update(action, reward, new_perception) -> None
get_state() -> dict
```

Rationale:

- generated files stay self-contained
- Phase 2 can load models dynamically
- no tight import dependency between generated code and simulator internals
- easier to inspect and test generated artifacts

Tradeoff:

- correctness depends on prompt and tests
- type checking is weaker than inheritance

The Builder prompt compensates by requiring deterministic structure, an inline
`Action` dataclass, read-only `decide`, mutating `update`, and `q_values` in
state.

## 5. Storage-First Artifacts

Decision: the runtime artifact source is MinIO/S3 plus Postgres metadata, not
local `outputs/` folders.

Rationale:

- web server, CLI and eval runs share the same artifact model
- pipeline state can be resumed independent of local disk
- generated models can be registered by S3 key
- traces and reports have stable run-scoped locations

Tradeoff:

- local debugging requires reading from object storage
- tests need fake or booted storage

## 6. Shared Services Instead of Globals

Decision: pass `Services` explicitly through entry points and Router.

Rationale:

- clearer dependency boundaries
- easier tests using fake services
- no hidden module state
- avoids Phase 1 <-> Phase 2 import cycles

Tradeoff:

- constructors carry more parameters
- more explicit wiring at entry points

This is the right tradeoff for a multi-service system where partial degradation
is expected.

## 7. Knowledge Backbone Uses Multiple Stores

Decision: use Postgres, MinIO, Neo4j and Qdrant together.

```text
MinIO    -> raw artifacts
Postgres -> lifecycle, confidence, temporal validity, metadata
Neo4j    -> graph identity and relations
Qdrant   -> dense/sparse similarity search
```

Rationale:

- no single store fits all access patterns
- graph traversal, vector search and temporal lifecycle are different problems
- separation makes failures easier to degrade

Tradeoff:

- operational complexity
- consistency logic required between stores

The current implementation reduces inconsistency by making Postgres the source
of truth for confidence and temporal validity.

## 8. Postgres Owns Temporal Truth

Decision: Neo4j relations link to Postgres memory rows by `memory_id`; Postgres
stores `valid_from`, `valid_to`, `confidence` and supersession.

Rationale:

- SQL is better for temporal validity and lifecycle queries
- confidence updates are atomic and indexed
- Qdrant payloads and Neo4j relations do not drift as sources of truth
- historical queries can be implemented by selecting valid memory ids first

Tradeoff:

- temporal graph queries need a two-step PG + Neo4j process
- relation inspection in Neo4j alone does not show full lifecycle state

## 9. Hybrid Retrieval Instead of One Search Method

Decision: combine dense vector search, sparse BM25 search and KG traversal.

Rationale:

- dense search captures semantic similarity
- sparse search captures exact terms, authors, DOIs and symbols
- KG traversal captures relations that are not text-nearest neighbors
- RRF fusion works without training data

Tradeoff:

- more moving parts
- retrieval latency needs active management

Latency is controlled by conditional shortcuts: skip KG NER when dense results
are strong, and skip CRAG when reranked results are already confident.

## 10. Corrective RAG With Web Fallback

Decision: retrieved memories are evaluated before injection when confidence is
not already high.

Rationale:

- stale or irrelevant memories can harm generation
- ambiguous stored results can be supplemented with fresh web context
- all-incorrect stored results can be replaced by web fallback

Tradeoff:

- extra model call in uncertain cases
- evaluator failure must be handled carefully

The implementation distinguishes "grader unavailable" from genuinely ambiguous
results to avoid unnecessary web-search storms.

## 11. Canonical Slugs and `__NEW__`

Decision: constrain paradigm identity through canonical slugs plus an explicit
new-paradigm escape.

Rationale:

- avoids duplicate concepts under many names
- improves cross-run retrieval
- makes eval metrics like slug accuracy meaningful
- keeps graph nodes stable

Tradeoff:

- true new paradigms require canonicalization logic
- overly broad canonicalization can merge concepts that should stay separate

The system uses candidate retrieval, enum-constrained structured output, ANN
search and a verify-merge gate to balance reuse and novelty.

## 12. Deterministic MemoryAgent

Decision: MemoryAgent is a fixed pipeline, not an open-ended conversational
agent.

Rationale:

- memory writes need predictable semantics
- failures can be isolated per step
- graph/vector/SQL writes require careful ordering
- results can be summarized as metrics

Tradeoff:

- less flexible than a general agent
- new memory behavior requires code changes

This distinction is important in the thesis: the project uses LLMs both as
creative agents and as structured assistants inside deterministic pipelines.

## 13. Parallel Fan-Out With Partial Failure

Decision: Formalizer, Reasoner and Builder launch sub-agents concurrently and
collect exceptions per item.

Rationale:

- paradigms and specs are independent units of work
- parallelism reduces wall time
- one failed sub-agent should not hide successful outputs from others

Tradeoff:

- logs and trace inspection become more important
- shared artifact paths must be stable

## 14. Prompt-Level Validation Plus Executable Tests

Decision: Reasoner and Builder prompts include explicit validation criteria;
Builder also runs tests.

Rationale:

- Reasoner catches conceptual/spec problems before code
- Builder catches implementability problems before writing model files
- tests provide executable evidence for generated code

Tradeoff:

- validation is partly LLM-mediated
- generated tests may miss behaviors not described in the spec

For the thesis, the important point is that validation exists at two levels:
semantic validation before code and executable validation after code.

## 15. Graceful Degradation

Decision: the pipeline should continue when optional memory infrastructure is
unavailable.

Rationale:

- research/code generation should not depend absolutely on Neo4j or Qdrant
- local development and tests remain simpler
- service outages do not destroy the full pipeline run

Tradeoff:

- output quality may be lower without retrieval
- memory metrics may be empty

Postgres and MinIO remain required because they are core persistence for the
pipeline itself.

## Known Documentation Drift

Some older design documents are still useful historically but no longer match
current code exactly. The most important differences:

- current code has Classifier and MemoryAgent in addition to the four main
  generation stages
- current artifacts are S3/MinIO-first, not local-output-first
- Qdrant currently stores `memories_dense` and `memories_sparse`, not four
  collections with artifact chunks
- Postgres currently owns temporal/confidence state, not Neo4j relations

Use this formal documentation folder as the current-code reference for the TFG.

## Code Anchors

- Router decisions: `src/decisionlab/router.py`
- Agent settings: `src/decisionlab/config.py`
- Research slug discipline: `src/decisionlab/agents/researcher.py`
- Canonicalization: `src/decisionlab/knowledge/canonicalize.py`
- MemoryAgent: `src/decisionlab/agents/memory_agent.py`
- Retrieval tool: `src/decisionlab/knowledge/retrieval/tool.py`
- Shared services: `../shared/shared/services.py`
- Memory lifecycle: `../shared/shared/pipeline_memories.py`

