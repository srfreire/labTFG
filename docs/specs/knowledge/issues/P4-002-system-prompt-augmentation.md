---
id: P4-002
title: Augment agent system prompts with knowledge retrieval instructions
status: in-progress
kind: strike
phase: 4
heat: agent-tools
priority: 2
blocked_by: [P4-001]
created: 2026-04-14
updated: 2026-04-15
---

# P4-002: Augment agent system prompts with knowledge retrieval instructions

## Objective
Add brief instructions to each pipeline agent's system prompt explaining when and how to use the `retrieve_knowledge` tool, so agents proactively query the knowledge backbone before generating new content.

## Requirements
- Each agent's system prompt constant (e.g., `RESEARCHER_SYSTEM_PROMPT`) gains a new section, conditionally appended only when the retrieve_knowledge tool is available

- **Researcher prompt addition:**
  ```
  ## Knowledge Backbone
  You have access to a knowledge backbone from past pipeline runs. Before starting web searches, call retrieve_knowledge to check if this problem domain has been researched before. Avoid redundant searches for paradigms already in the knowledge base. Use retrieved knowledge to inform your paradigm identification and cross-paradigm interaction analysis.
  ```

- **DeepResearcher prompt addition:**
  ```
  ## Knowledge Backbone
  You have access to a knowledge backbone from past pipeline runs. Before starting your research loop, call retrieve_knowledge to find existing deep research on this paradigm. Build on existing postulates, variables, and references rather than starting from scratch. Use retrieved knowledge to identify gaps in existing coverage.
  ```

- **Formalizer prompt addition:**
  ```
  ## Knowledge Backbone
  You have access to a knowledge backbone from past pipeline runs. Before writing formulations, call retrieve_knowledge to find mathematical formulation patterns that have worked for similar paradigms. Reference existing equations, parameter sources, and proven mathematical structures.
  ```

- **Reasoner prompt addition:**
  ```
  ## Knowledge Backbone
  You have access to a knowledge backbone from past pipeline runs. Before adapting formulations to the environment, call retrieve_knowledge to find validated parameter ranges and env_mapping patterns from past runs. Use proven defaults and mapping strategies when available.
  ```

- **Builder prompt addition:**
  ```
  ## Knowledge Backbone
  You have access to a knowledge backbone from past pipeline runs. Before generating code, call retrieve_knowledge to find working code patterns, test strategies, and common pitfalls from past model builds. Apply proven implementation patterns when the mathematical structure is similar.
  ```

- Prompt sections are conditionally appended: only when `retrieve_knowledge` tool is in the tool list. This prevents confusing agents about a tool they don't have.

## Acceptance Criteria
- [ ] AC1: When knowledge infrastructure is available, each agent's system prompt contains the "Knowledge Backbone" section
- [ ] AC2: When knowledge infrastructure is unavailable, system prompts are unchanged from current behavior
- [ ] AC3: The Researcher calls retrieve_knowledge early in its loop (before web_search) when relevant past knowledge exists
- [ ] AC4: The Formalizer references retrieved formulation patterns in its output when available
- [ ] AC5: Prompt additions are concise (under 80 words each) — no system prompt bloat

## Files Likely Affected
- `phase1-pablo/src/decisionlab/agents/researcher.py` — RESEARCHER_SYSTEM_PROMPT modification
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — DEEP_RESEARCHER_SYSTEM_PROMPT modification
- `phase1-pablo/src/decisionlab/agents/formalizer_sub.py` — FORMALIZER_SUB_SYSTEM_PROMPT modification
- `phase1-pablo/src/decisionlab/agents/reasoner_sub.py` — REASONER_SUB_SYSTEM_PROMPT modification
- `phase1-pablo/src/decisionlab/agents/builder_sub.py` — BUILDER_SUB_SYSTEM_PROMPT modification

## Context
Phase spec: `docs/specs/knowledge/phase-4-pipeline-integration.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `agent-tools`
Depends on P4-001 — prompts reference the tool, so it must exist first.
