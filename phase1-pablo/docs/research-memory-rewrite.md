# Research → Memory contract rewrite

A clean rewrite of the Researcher → MemoryAgent boundary and the
identifier propagation across Formalizer → Reasoner → Builder.
Driven by failure modes observed in the `cumulative-growth` and
`memory-retrieval` evals.

**Model constraint**: every LLM call introduced or modified by this
rewrite must use `anthropic/claude-sonnet-4.6` — same as the existing
agent stages. No Haiku, no Opus, no provider variance.

## Why this rewrite

Two evals (5+3 topics, $6.73 total) surfaced a pattern of small,
related failures that share a common cause: the system has no
authoritative entity registry, so each agent invents identifiers
freely and the persistence layer absorbs whatever it gets.

Concrete failures:

1. **Slug fragmentation at the Researcher**. On `cumulative-growth`
   topic 1 and `memory-retrieval` topic 1, the Researcher emitted
   `q-learning`, `temporal-difference-learning`, `optimal-foraging-theory`
   instead of the umbrella `reinforcement-learning` already in the KG.
   `paradigm: reinforcement-learning` failed both times.
2. **Other agents free-invent identifiers too**. Formalizer's
   `formulation_id`, Reasoner's `spec_id`, Builder's class names —
   nothing constrains them to reference the Researcher's slug.
3. **Variables and Postulates fragment**. 84 Variables, 99
   Postulate→Paradigm BELONGS_TO edges; "reward" / "expected reward" /
   "reward signal" can dup just like paradigms.
4. **MemoryAgent re-extracts entities from prose**. Even with a
   constrained slug output, the report text is entity-extracted; new
   Paradigm nodes can still be minted from prose mentions.
5. **Write-path bug**. `Neo.ClientError.Schema.ConstraintValidationFailed`
   on `Paper.doi` voided every KG write for a single topic
   (`cumulative-growth` topic 1: `nodes_created=0`).
6. **Silent JSON-parse fallback**. `_score_importance` fired on every
   topic with `WARNING Importance scoring failed — defaulting all
   facts to 5.0`. Importance values are persistently wrong.
7. **Eval blindness**. Assertions only inspect Neo4j; Qdrant memories
   and Postgres confidence are never checked. We don't know whether
   `retrieve_knowledge` is even being called.
8. **Search-cap exhaustion**. DuckDuckGo "No results" repeatedly
   blew the DeepResearcher 7-iteration cap.

None of these need patches. They need a rewrite of the contract.

## New architecture

### Researcher — gap-fill instead of free research

The Researcher's first action is mandatorily a `retrieve_knowledge`
call against the topic, scoped to `label=Paradigm`. The result —
top-K candidate slugs with their definitions — becomes the candidate
list for a coverage-assessment LLM step that decides what's missing.
Web search only fires on the gap claims.

Output uses Anthropic Structured Outputs (Sonnet 4.6) with this shape:

```python
class ParadigmEmission(BaseModel):
    slug: Literal[<known-slugs>, "__NEW__"]
    slug_proposal: str | None  # required iff slug == "__NEW__"
    definition: str
    rationale: str  # why this paradigm explains the topic

class ResearcherOutput(BaseModel):
    paradigms: list[ParadigmEmission]
    citations: list[Citation]
```

The `Literal[<known-slugs>, "__NEW__"]` enum is computed at request
time from the `retrieve_knowledge` result. The model literally cannot
emit a slug outside the candidate set or `__NEW__`.

### Canonicalizer — new stage in MemoryAgent

Inserted between extraction and KG write. For every entity emitted
with `slug == "__NEW__"` *or* extracted from prose during MemoryAgent's
own entity extraction:

1. Embed `slug_proposal + definition` via Voyage.
2. Cosine-match against existing same-label node embeddings.
3. If `max_sim >= τ` (default 0.85): an LLM verification step
   (Sonnet 4.6, Structured Outputs) decides merge vs. keep separate.
4. Below τ: register as a new node.

Applies to **Paradigm, Variable, Postulate** — not just paradigms.
Paper canonicalization stays DOI-keyed.

### Slug propagation downstream

Each downstream agent's identifier is enum-constrained against the
upstream stage's emissions:

| Stage | Emits | Constraint |
|---|---|---|
| Researcher | `paradigm.slug` | enum from KG retrieve result + `__NEW__` |
| Formalizer | `formulation_id` | enum from approved paradigm slugs |
| Reasoner | `spec_id` | enum from approved formulation_ids |
| Builder | model class name | derived from `spec_id` (no LLM choice) |

Cross-stage drift becomes structurally impossible.

### Write hardening

- Per-entity Neo4j transactions: a single `Paper.doi` collision can
  no longer void the rest of the batch.
- `Paper`: `MERGE (p:Paper {doi: $doi}) ON CREATE SET ... ON MATCH SET ...`
  instead of `CREATE` + catch.
- Failed entity writes log a `kg_write_skipped` event captured in the
  trace; downstream assertions can detect partial writes.

### Structured Outputs everywhere JSON is parsed

A small `decisionlab.structured` wrapper:

```python
async def call_structured(
    *, client, messages, system, schema: type[T], max_tokens: int = 4096,
) -> T:
    """Sonnet 4.6 + Anthropic Structured Outputs + Pydantic validation.
    Raises StructuredOutputError on schema violation (no silent fallback)."""
```

Migration targets: `_score_importance`, every entity extraction
prompt, every agent's final emission. Parse failures raise loudly
(caught at the stage handler, surfaced in the trace) instead of
defaulting to 5.0.

### Eval instrumentation

`PipelineRunResult` extended with:

```python
@dataclass(frozen=True)
class ToolCall:
    name: str
    stage: Stage
    args_hash: str
    succeeded: bool

class PipelineRunResult:
    ...
    tool_call_log: tuple[ToolCall, ...]
```

New assertion predicates:

| Name | Args | Pass when |
|---|---|---|
| `tool_called` | `{name, min}` | `len([c for c in log if c.name == name]) >= min` |
| `min_memories` | `{namespace, n}` | Qdrant memory collection count ≥ n |
| `paradigm_reused` | slug | KG paradigm node's `valid_from` < this run's `started_at` (proves the run hit an existing node, not minted one) |
| `confidence_above` | `{fact_substring, threshold}` | Postgres memory row's confidence ≥ threshold |

### Provider failover for web search

`adapters/__init__.py` exposes a chained search adapter:

```python
SearchProviderChain([BraveAdapter(), TavilyAdapter(), DuckDuckGoAdapter()])
```

Each provider has a 3-attempt cap before failover. The chain returns
empty only when every provider returned empty.

## Build sequence

Each phase has a verification step. A phase doesn't land until its
verification passes against a real eval run.

| Phase | What | Effort | Verification |
|---|---|---|---|
| **A** | Instrumentation: tool-call log + new predicates + DOI MERGE fix + Brave/Tavily failover + delete `shared/tokenizer.py` | 0.5 d | `cumulative-growth` re-runs; tool-call counts visible in report; topic-1 DOI failure no longer voids writes |
| **B** | `decisionlab.structured` wrapper + migrate `_score_importance` + extraction prompts to Structured Outputs | 0.5 d | zero `Importance scoring failed` warnings across `cumulative-growth` |
| **C** | Researcher rewrite: mandatory `retrieve_knowledge`, gap-only web search, enum-constrained Structured Output | 1 d | slug retrieval hit rate ≥ 80% on `memory-retrieval` (baseline 67%); tool_called(retrieve_knowledge, min=1) passes for every topic |
| **D** | Canonicalizer stage in MemoryAgent for Paradigm/Variable/Postulate | 1 d | KG growth ratio < 30 nodes/topic on populated KG (baseline 44); new `paradigm_reused` assertion passes for known slugs |
| **E** | Identifier propagation: Formalizer/Reasoner/Builder enum-constrained on upstream | 0.5 d | full-pipeline run produces consistent identifiers across all 4 stages — Researcher slug → Formalizer formulation_id → Reasoner spec_id → Builder class name |
| **F** | Validate: rerun both suites + new `paradigm-canonicalization.yaml` regression suite | 0.5 d | all suites pass; metrics table written to report; comparison vs pre-rewrite baseline |

**Total: ~4 days.**

## Files

### New (4)

- `src/decisionlab/canonicalize.py` — embedding cosine + LLM verify
- `src/decisionlab/structured.py` — Sonnet 4.6 + Pydantic wrapper
- `src/decisionlab/adapters/brave.py` + provider chain in `adapters/__init__.py`
- `evals/suites/paradigm-canonicalization.yaml` — regression suite

### Modified (~14)

- `src/decisionlab/agents/researcher.py` — major rewrite
- `src/decisionlab/agents/memory_agent.py` — canonicalize step
- `src/decisionlab/agents/formalizer.py` — enum-constrained id
- `src/decisionlab/agents/reasoner.py` — same
- `src/decisionlab/agents/builder.py` — derive class name
- `src/decisionlab/knowledge/resolver.py` — structured `_score_importance`
- `src/decisionlab/knowledge/kg_writer.py` — per-entity tx + DOI MERGE
- `src/decisionlab/knowledge/extraction.py` — Structured Outputs
- `src/decisionlab/eval/assertions.py` — new predicates
- `src/decisionlab/eval/models.py` — `tool_call_log`
- `src/decisionlab/eval/runner.py` — capture tool calls
- `src/decisionlab/router.py` — thread slugs across stages
- `src/decisionlab/adapters/__init__.py` — provider chain

### Deleted

- `shared/shared/tokenizer.py` — confirmed dead code; sparse write
  path already uses `Document(text=..., model="Qdrant/bm25")`.

## Decisions (formerly open questions)

1. **Model**: `anthropic/claude-sonnet-4.6` for every LLM call —
   Researcher, Canonicalizer, importance scoring, entity extraction,
   structured emissions. No model variance across this rewrite.

2. **Structured Outputs adoption**: Anthropic Structured Outputs
   (released 2025-11-14) is supported by Sonnet 4.6 and is grammar-level
   — the model literally cannot emit off-schema tokens. Use it directly
   via `output_format={"type": "json_schema", "schema": ...}` rather
   than fall back to forced tool-use + Pydantic validation. The
   `decisionlab.structured` wrapper hides the boilerplate.

3. **Cosine threshold τ**: start at 0.85 (Voyage `voyage-4-lite`
   embeddings — empirically the cluster boundary in the KG-empowered
   KGC survey, arXiv:2510.20345). Phase D adds a 50-pair labeled
   mini-set under `evals/fixtures/canonicalize-pairs.json` to tune. If
   precision/recall on that set is below 0.9 at τ=0.85, ratchet up to
   0.88 or split into per-label thresholds (Paradigm typically needs
   higher than Variable).

4. **Search provider order**: `Brave → Tavily → DuckDuckGo`. Brave
   leads agent-search benchmarks (14.89 score / 669 ms in Firecrawl's
   2026 review), has a free tier, and the API key is already in
   `.env`. Tavily handles the rare cases Brave misses on academic
   queries. DuckDuckGo stays as final fallback because it's keyless.

5. **Canonicalizer merge approval**: auto-merge above τ for eval runs
   (`AutoApproveFeedback`); for `decisionlab run` (interactive), surface
   merges to a CLI confirmation before commit. Web pipeline routes
   through `WebFeedback` and gets a `confirm_canonicalize_merge`
   prompt. The `FeedbackPort` protocol gains one method:

   ```python
   async def confirm_canonicalize_merge(
       self, candidate: str, target: str, similarity: float, definition: str,
   ) -> bool: ...
   ```

   `AutoApproveFeedback.confirm_canonicalize_merge` returns
   `similarity >= τ`. CLI prompts. Web emits a question.

6. **Backward compat**: drop existing runs. Run rows in Postgres are
   research artifacts, not user data. KG state from
   `cumulative-growth` + `memory-retrieval` (633 nodes, 347 relations)
   gets reset before Phase F validation runs. S3 reports stay (read-
   only); they're addressed by `run_id` so old keys don't collide
   with new ones.

## Verification metrics (pre/post)

| Metric | Pre (cumulative-growth + memory-retrieval) | Target (post-rewrite) |
|---|---:|---:|
| Slug retrieval hit rate (named slug) | 67% (2/3) | ≥ 80% |
| KG nodes per topic on populated KG | 44 | < 30 |
| `Importance scoring failed` per topic | 1 | 0 |
| Topics with `nodes_created=0` (write voided) | 1/8 | 0 |
| Eval predicate coverage | Neo4j only | Neo4j + Qdrant + Postgres + tool-call |
| DeepResearcher max-iter exhaustions | observed (count not tracked) | tracked + < 5% of launches |
| Cross-stage identifier alignment | not checked | 100% (enforced by enum) |

## Out of scope

Deliberately deferred — listed so we don't scope-creep:

- **Vector-seeded graph traversal (HippoRAG-style)** as a second
  retrieval tool. The current parallel-RRF pipeline handles single-
  entity lookup well; multi-hop queries aren't yet a measured pain.
- **`SIMILAR_TO` / `GENERALIZES` cross-paradigm edges**. Pays off
  only after canonicalization reduces duplication; otherwise we'd
  draw edges between near-duplicates.
- **LLM record/replay fixtures** for zero-cost CI evals. Listed in
  `eval-system.md` roadmap; this rewrite doesn't depend on it.
- **Phase 2 (`simlab`) integration**. Phase 2's `retrieve_knowledge`
  consumer isn't blocked by these changes.

## Roll-out

Each phase commits independently with `feat[phase1]:` /
`fix[phase1]:` / `test[phase1]:` prefixes per repo convention. No
push between phases — push happens once after Phase F's metrics
table confirms all targets met.
