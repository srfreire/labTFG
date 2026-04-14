---
id: P2-001
title: Build entity and relation extraction module with stage-specific Haiku prompts
status: done
kind: strike
phase: 2
heat: extraction
priority: 1
blocked_by: []
created: 2026-04-14
updated: 2026-04-15
---

# P2-001: Build entity and relation extraction module with stage-specific Haiku prompts

## Objective
Create the core extraction logic that takes a pipeline stage's output text and produces structured entities, relations, and plain-text facts using Haiku LLM calls with stage-specific prompts.

## Requirements
- Module: `phase1-pablo/src/decisionlab/knowledge/extraction.py`
- Prompts module: `phase1-pablo/src/decisionlab/knowledge/prompts.py` — stage-specific system/user prompts as constants

- Output dataclasses:
  ```python
  @dataclass
  class NodeSpec:
      label: str           # Neo4j label: Paradigm, Variable, Paper, etc.
      properties: dict     # all properties for the node
      natural_key: str     # property name used for dedup (e.g., "slug", "doi", "id")

  @dataclass
  class RelationSpec:
      from_label: str
      from_key_value: str  # natural key value of source node
      to_label: str
      to_key_value: str    # natural key value of target node
      rel_type: str        # SUPPORTS, CONTRADICTS, etc.
      properties: dict     # confidence, quote, etc.

  @dataclass
  class ExtractionResult:
      nodes: list[NodeSpec]
      relations: list[RelationSpec]
      facts: list[str]     # plain-text memory facts (atomic statements)
      stage: str           # which stage produced this
      run_id: str
  ```

- `async extract(stage: str, output_text: str, run_id: str, client: AsyncAnthropic) -> ExtractionResult`
  - Dispatches to stage-specific extraction function based on `stage` parameter
  - Each stage function builds a prompt, calls Haiku, parses the structured JSON response

- Stage-specific extraction prompts:
  - **`extract_from_research(text)`**: Input is DeepResearcher markdown report. Extract: Paradigm (name, slug, description), Author (name, affiliation), Paper (title, year, doi, citation_count — parse from the References section and inline citations), BrainRegion (name, system), Variable (name, type, range, unit — from the "Identified Variables" table), Postulate (id like P1/P2/P3, statement, falsifiable boolean). Relations: BELONGS_TO (Postulate→Paradigm), AUTHORED (Author→Paper), SUPPORTS (Paper→Postulate with quote), MEASURES (Variable→BrainRegion). Facts: one atomic fact per postulate, one per variable's role.
  - **`extract_from_formalization(text)`**: Input is Formalizer markdown with LaTeX. Extract: Equation (latex, plaintext, type), Variable (name, type — may overlap with research vars, dedup by name), Parameter (name, default_value, source, range — from Parameters tables). Relations: USES_EQUATION (Formulation→Equation), MODULATES (Variable→Variable with direction and equation_ref). Facts: one fact per equation's meaning, one per parameter's source.
  - **`extract_from_reasoner(text)`**: Input is Reasoner JSON spec. Extract: Parameter (name, default_value updated from spec, range), env_mapping info. Relations: DERIVES_FROM (Parameter→Postulate with derivation_chain — trace which postulate justifies each parameter). Facts: one fact per validation check passed/failed, one per env_mapping decision.
  - **`extract_from_builder(text)`**: Input is Builder Python code + test results. Extract: Model (formulation_id, class_name), TestResult (formulation_id, passed, failure_reason). Relations: IMPLEMENTS (Model→Formulation). Facts: one fact per test outcome, one per notable code pattern (e.g., "uses Q-learning with softmax", "implements PI controller with anti-windup").

- Haiku response format: instruct Haiku to output JSON matching `{"nodes": [...], "relations": [...], "facts": [...]}`. Parse with `json.loads`. Handle malformed JSON gracefully (retry once, then return partial result with warning).

## Acceptance Criteria
- [x] AC1: `extract("researcher", deep_report_text, run_id, client)` on the sample homeostatic-regulation report produces NodeSpecs for: >=1 Paradigm, >=2 Authors, >=3 Papers, >=3 Variables, >=2 Postulates
- [x] AC2: `extract("formalizer", formulation_text, run_id, client)` on the sample homeostatic formulations produces NodeSpecs for: >=2 Equations, >=3 Parameters with default values and sources
- [x] AC3: `extract("reasoner", reasoner_json, run_id, client)` produces RelationSpecs with DERIVES_FROM linking parameters to postulates
- [x] AC4: `extract("builder", model_code, run_id, client)` produces a Model NodeSpec with correct class_name and a TestResult with passed=True
- [x] AC5: Each extraction produces >=3 plain-text facts that are atomic statements (not compound sentences)
- [x] AC6: Malformed Haiku JSON triggers one retry; if retry also fails, returns partial ExtractionResult with available data + logs warning

## Files Likely Affected
- `phase1-pablo/src/decisionlab/knowledge/__init__.py` — new package
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — extraction logic
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — prompt constants
- `phase1-pablo/src/decisionlab/knowledge/models.py` — dataclasses (NodeSpec, RelationSpec, ExtractionResult)

## Context
Phase spec: `docs/specs/knowledge/phase-2-memory-agent.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `extraction`
This is the foundation — all other Phase 2 issues consume ExtractionResult.

## Completion Summary

**Commit:** `c371763` — `feat[knowledge]: entity and relation extraction module (P2-001)`

### What was built
- Knowledge extraction module with stage-specific Haiku prompts for all 4 pipeline stages
- `extract()` async dispatcher that calls Haiku, parses JSON, retries on malformed response
- Robust handling: empty API content → retry, curly braces in output text, markdown-fenced JSON
- 22 tests covering all 6 acceptance criteria plus edge cases

### Files created/modified
- `phase1-pablo/src/decisionlab/knowledge/__init__.py` — new package exposing extract + dataclasses
- `phase1-pablo/src/decisionlab/knowledge/models.py` — NodeSpec, RelationSpec, ExtractionResult
- `phase1-pablo/src/decisionlab/knowledge/prompts.py` — stage-specific system/user prompts
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — extract(), _call_haiku(), _try_parse_json(), _build_result()
- `phase1-pablo/tests/knowledge/test_extraction.py` — 22 unit tests with realistic mock Haiku responses

### Decisions
- Used `str.replace` instead of `str.format` for user prompt templating to avoid KeyError on JSON input containing curly braces
- Return empty string on empty API content list (triggers existing retry path cleanly)
- Narrowed except to `json.JSONDecodeError` only (was redundantly catching parent `ValueError`)
