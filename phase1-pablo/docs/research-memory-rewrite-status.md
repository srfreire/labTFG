# Research → Memory rewrite — status

Implementation status against `docs/research-memory-rewrite.md`. Phases
A–E have landed; Phase F ships the regression suite + labeled fixture
but **does not** include the live eval rerun (that costs real API budget
and requires Neo4j/Qdrant/Postgres up).

To run Phase F validation against live infra:

```bash
cd phase1-pablo
uv run decisionlab kg reset --confirm   # if you want a clean baseline
uv run decisionlab eval run evals/suites/cumulative-growth.yaml
uv run decisionlab eval run evals/suites/memory-retrieval.yaml
uv run decisionlab eval run evals/suites/paradigm-canonicalization.yaml
```

Then compare the produced report's metrics against the target table at
the bottom of this document.

## What landed per phase

| Phase | Effort | Files | Tests |
|---|---|---|---|
| A — instrumentation | 0.5 d | `runtime/tool_calls.py` (new), `runtime/dispatcher.py` (hook), `eval/models.py` + `eval/runner.py` (capture), `eval/assertions.py` (4 new predicates), `eval/suite.py` (KG-assertion list), `knowledge/kg_writer.py` (per-entity tx + DOI MERGE), `adapters/__init__.py` + `adapters/brave.py` + `adapters/tavily.py` (failover chain), `cli.py` / `cli_eval.py` / `server.py` (chain wiring), `shared/tokenizer.py` (deleted) | existing 749 stay green, no new |
| B — structured outputs | 0.5 d | `structured.py` (new wrapper), `knowledge/resolver.py` (`_score_importance` + `_classify_conflict`), `knowledge/extraction.py` (every stage), `knowledge/prompts.py` (importance prompt slimmed) | rewrote `test_extraction.py`, replaced silent-fallback tests in `test_resolver.py`, fixed `test_confidence_evolution.py` mock |
| C — Researcher rewrite | 1.0 d | `agents/researcher.py` (3-step pipeline + dynamic Pydantic Literal slug enum) | 10 researcher tests still green; `test_prompt_augmentation.py` updated for the new contract |
| D — Canonicalizer | 1.0 d | `canonicalize.py` (new), `agents/memory_agent.py` (call site), `feedback_port.py` (`confirm_canonicalize_merge` on every port) | 5 hermetic `test_canonicalize.py` cases |
| E — identifier propagation | 0.5 d | `agents/builder_sub.py` (`derive_class_name`, prompt requires it), `router.py` (registry uses derived name; reasoner JSON `formulation_id` re-pinned to filename) | 9 `test_router_review_build` cases updated |
| F — validation artifacts | 0.5 d | `evals/suites/paradigm-canonicalization.yaml` (new regression suite), `evals/fixtures/canonicalize-pairs.json` (18 labeled pairs for τ tuning), `tests/eval/test_phase_f_artifacts.py` (static checks) | 6 static-validation tests |

## Failure-mode coverage

| Failure observed in pre-rewrite evals | How the rewrite prevents it |
|---|---|
| Slug fragmentation (`q-learning` instead of `reinforcement-learning`) | Phase C: Researcher's final emission is enum-constrained against retrieved KG slugs + `__NEW__`. Phase D: Canonicalizer catches drift even when `__NEW__` is emitted. |
| Other agents free-invent identifiers | Phase E: Builder class name is derived from spec_id; Reasoner JSON `formulation_id` is re-pinned to the filename. Formalizer formulations are constrained by the paradigm slug it's writing for (state.approved_paradigms). |
| Variable / Postulate fragmentation | Phase D: Canonicalizer applies to Paradigm, Variable, **and** Postulate. |
| MemoryAgent re-extracts entities from prose | Phase D's canonicalizer runs on every extraction (whether sourced from structured emission or extracted from prose) — so prose-minted Paradigm/Variable/Postulate nodes also go through cosine + LLM verify before hitting the KG. |
| Single Paper.doi collision voids the whole topic's writes | Phase A: per-entity managed-write transactions; `_resolve_natural_key` prefers the schema's unique key. |
| Silent JSON-parse fallback (`Importance scoring failed → all 5.0`) | Phase B: `call_structured` raises `StructuredOutputError` on schema violation. The pre-rewrite warning-and-default path is gone for importance scoring; conflict classification still catches broadly but now logs at WARNING instead of fabricating UNKNOWN silently. |
| Eval blindness (Neo4j-only assertions) | Phase A: `tool_called`, `min_memories`, `confidence_above`, `paradigm_reused` predicates added. Phase F regression suite uses `tool_called` to prove `retrieve_knowledge` fires on every topic. |
| DuckDuckGo "No results" exhausting the iteration cap | Phase A: `SearchProviderChain([Brave, Tavily, DuckDuckGo])` with 3-attempt retry per provider. |

## Verification metrics — pre vs target

These are the targets from the plan. Filling in the post-rewrite column
requires actually running Phase F suites against live infra.

| Metric | Pre (cumulative-growth + memory-retrieval) | Target (post-rewrite) | Post (run to fill) |
|---|---:|---:|---:|
| Slug retrieval hit rate (named slug) | 67% (2/3) | ≥ 80% | _tbd_ |
| KG nodes per topic on populated KG | 44 | < 30 | _tbd_ |
| `Importance scoring failed` per topic | 1 | 0 | _tbd_ |
| Topics with `nodes_created=0` (write voided) | 1/8 | 0 | _tbd_ |
| Eval predicate coverage | Neo4j only | Neo4j + Qdrant + Postgres + tool-call | **done** |
| DeepResearcher max-iter exhaustions | observed | tracked + < 5% | _tbd_ |
| Cross-stage identifier alignment | not checked | 100% (enforced by enum / derivation) | **done** |

## Out-of-scope items (deferred from the plan)

Same as the plan's "Out of scope" section, untouched:

- Vector-seeded graph traversal (HippoRAG-style)
- `SIMILAR_TO` / `GENERALIZES` cross-paradigm edges
- LLM record/replay fixtures for zero-cost CI evals
- Phase 2 (`simlab`) integration of the new contract
