# Formal Documentation - Phase 1

This folder documents the real Phase 1 system for the TFG memory. It focuses on
Pablo's part of the project and on the shared infrastructure that Phase 1 uses.
Juan's Phase 2 application is only mentioned where the shared schema or
DecisionModel contract makes the boundary relevant.

The goal is not to duplicate every prompt or class. The goal is to provide a
clear technical base for the thesis: architecture, agent workflow, memory
system, infrastructure responsibilities, and key design decisions.

## Document Map

| File | Purpose |
| --- | --- |
| `01-system-architecture.md` | Global view of Phase 1, modules, storage, runtime, and boundaries. |
| `02-agent-workflow.md` | Deep explanation of the agent pipeline from problem statement to Python models. |
| `03-memory-and-knowledge-system.md` | Deep explanation of the knowledge backbone, retrieval, MemoryAgent, and temporal memory. |
| `04-shared-infrastructure.md` | Shared services used by Phase 1: Postgres, MinIO, Neo4j, Qdrant, embeddings. |
| `05-key-design-decisions.md` | Rationale for the main design choices and important tradeoffs. |

## Scope

In scope:

- `phase1-pablo/src/decisionlab`
- `phase1-pablo/examples/sample-run`
- `phase1-pablo/tests` only as evidence of intended behavior
- `shared/shared` where directly used by Phase 1
- root `docs/specs/knowledge` and `docs/specs/memory-refactor` as historical design context

Out of scope:

- Phase 2 application internals
- UI details beyond the fact that Router emits trace/status events
- exhaustive prompt reproduction
- thesis prose polish

## Current System Summary

Phase 1 is a multi-agent research and code-generation pipeline. It receives a
decision-making problem in natural language and produces executable Python
decision models. The pipeline is coordinated by a Router and implemented through
specialized agents:

```text
Problem
  |
  v
Classifier -> Researcher -> Formalizer -> Env spec input -> Reasoner -> Builder
                 |             |                            |          |
                 v             v                            v          v
              research      math formulations              JSON       Python
              reports                                      specs      models
```

When memory infrastructure is available, accepted stage outputs are also written
to a persistent knowledge backbone:

```text
Approved stage output
  -> MemoryAgent
  -> structured extraction
  -> Neo4j graph + Qdrant memory vectors + Postgres lifecycle rows
```

The important architectural distinction is this:

- The agents generate research, mathematical specifications and code.
- The memory system curates accepted outputs into reusable knowledge.
- The shared infrastructure stores artifacts, runs, models and memory state.

## Primary Source Files

Main orchestration and agent code:

- `src/decisionlab/router.py`
- `src/decisionlab/agents/researcher.py`
- `src/decisionlab/agents/deep_researcher.py`
- `src/decisionlab/agents/formalizer.py`
- `src/decisionlab/agents/formalizer_sub.py`
- `src/decisionlab/agents/reasoner.py`
- `src/decisionlab/agents/reasoner_sub.py`
- `src/decisionlab/agents/builder.py`
- `src/decisionlab/agents/builder_sub.py`
- `src/decisionlab/agents/memory_agent.py`

Shared infrastructure:

- `../shared/shared/services.py`
- `../shared/shared/models.py`
- `../shared/shared/storage.py`
- `../shared/shared/database.py`
- `../shared/shared/knowledge_graph.py`
- `../shared/shared/vector_store.py`
- `../shared/shared/embedding.py`
- `../shared/shared/pipeline_memories.py`

