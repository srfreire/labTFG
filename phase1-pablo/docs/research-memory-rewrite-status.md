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

## Verification metrics — pre vs target vs post

Live-infra runs on 2026-05-07: `smoke` → `cumulative-growth` → `memory-retrieval`
→ `paradigm-canonicalization`, total cost $18.84.

| Metric | Pre | Target | Post | Status |
|---|---:|---:|---:|---|
| Slug retrieval hit rate (named slug) | 67% (2/3) | ≥ 80% | 50% (3/6 across mem-retrieval + paradigm-canon) | ❌ regressed |
| KG nodes per topic on populated KG | 44 | < 30 | ~84 avg (range 40–141) | ❌ worse |
| `Importance scoring failed` per topic | 1 | 0 | 0 across all 12 topics | ✅ fixed |
| Topics with `nodes_created=0` (write voided) | 1/8 | 0 | 0/12 | ✅ fixed |
| Eval predicate coverage | Neo4j only | Neo4j + Qdrant + Postgres + tool-call | tool_call_log serialized to JSON, `tool_called` / `paradigm_reused` / `min_memories` / `confidence_above` all wired | ✅ done |
| DeepResearcher max-iter exhaustions | observed | tracked + < 5% | 4 hits across 12 topics (33%) | ❌ above target |
| Cross-stage identifier alignment | not checked | 100% (enforced by enum / derivation) | enforced via Phase E derivation | ✅ done |
| `tool_called(retrieve_knowledge)` per topic | not measured | ≥ 1 | passes 12/12 (1–12 calls each) | ✅ Phase A working |
| Canonicalizer merge rate on populated KG | not measured | qualitative | T2 paradigm-canon: 27/40 (68%) merges; T1: 34/40 (85%); T4 (negative control): 17/135 (13%) | ✅ working |

### Headline reading

**The rewrite achieved its silent-failure goals (Phase A/B) but missed its
slug-fragmentation goals (Phase C).** Phase D is doing real work — the
canonicalizer correctly merges 60–85% of new entities on populated KG when
topics overlap with prior knowledge, and stays appropriately low (13%) when
topics introduce new territory. Phase A instrumentation works in-memory but
required a JSON-renderer fix (this run) to be visible in reports.

**Phase C (umbrella-slug retrieval) underperformed** because the populated
KG never accumulates the canonical umbrella slugs (`reinforcement-learning`,
`prospect-theory`, `bounded-rationality`, `free-energy-principle`) — the
Researcher consistently emits more specific variants (`q-learning`,
`td-rl-foraging`, `loss-aversion`, `regret-theory`, `active-inference`).
The retrieve_knowledge mandate is firing (4–12 calls/topic) but its
candidate set never contains the umbrella, so the enum-constrained emission
rules out the umbrella by construction. `prospect-theory` only entered the
KG via canonicalizer merging variants together across runs (visible as
`paradigm_reused` PASS in paradigm-canon T2).

### Bugs surfaced and fixed during this validation run

1. **`call_structured` non-streaming timeout**: extraction's `_MAX_TOKENS=32768`
   tripped Anthropic SDK's 10-minute non-streaming guard, causing every
   Memory Agent extraction to fail with `ValueError: Streaming is required...`.
   Fixed by mirroring `runtime/loop.py`'s `max_tokens >= 24000 → stream`
   pattern in `structured.py`. Without this fix, smoke produced
   `nodes_created=0` even though the eval suite reported PASS.

2. **`tool_call_log` not serialized to JSON report**: `eval/report.py:render_json`
   never wrote the `PipelineRunResult.tool_call_log` field, making Phase A
   instrumentation appear broken when reading from `report.json`. The
   in-memory list was always populated correctly (the `tool_called`
   assertion read from it directly), but post-hoc analysis was blind.
   Fixed by adding `"tool_call_log": [asdict(c) for c in tr.run.tool_call_log]`
   to the per-topic `run` dict.

### Known issues not addressed by this rewrite

- **Reflection generation still uses non-structured JSON parse** — `Reflection
  generation failed for cluster (size=N): Expecting value: line 1 column 1
  (char 0)` warnings recur across every suite. Separate from the Phase B
  extraction fix; needs `call_structured` migration of the reflection path.
- **UUID slug bug**: `Paradigm` node `a6744d26-a84e-454a-bc0f-f0fc3b161905`
  appeared in the KG after cumulative-growth re-run — a UUID being used as
  a Paradigm.slug somewhere. Not investigated.
- **DeepResearcher max-iter exhaustion at 33%** is well above the < 5%
  target. The provider chain (Brave → Tavily → DuckDuckGo) didn't measurably
  reduce this; the iteration-cap pressure may come from something other
  than empty search results.

## Out-of-scope items (deferred from the plan)

Same as the plan's "Out of scope" section, untouched:

- Vector-seeded graph traversal (HippoRAG-style)
- `SIMILAR_TO` / `GENERALIZES` cross-paradigm edges
- LLM record/replay fixtures for zero-cost CI evals
- Phase 2 (`simlab`) integration of the new contract
