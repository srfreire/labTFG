---
id: P1-002
title: Add Postgres memories table with SQLAlchemy model
status: in-progress
kind: strike
phase: 1
heat: data-model
priority: 2
blocked_by: [P1-001]
created: 2026-04-14
updated: 2026-04-14
---

# P1-002: Add Postgres memories table with SQLAlchemy model

## Objective
Extend the existing `shared/models.py` with a `Memory` SQLAlchemy model for storing structured memory metadata. The actual embeddings live in Qdrant — this table stores content, confidence, provenance, and temporal validity.

## Requirements
- SQLAlchemy async model `Memory` added to `shared/models.py`, following the existing pattern (UUID PK, declarative base, async engine)
- Columns:
  - `id`: UUID, primary key, server_default=uuid4
  - `content`: Text, not null — the memory fact text
  - `namespace`: String, not null — one of: paradigm, formulation, model, simulation, meta
  - `memory_type`: String, not null — one of: episodic, semantic, procedural, reflection
  - `source_stage`: String, not null — which pipeline stage produced this (researcher, formalizer, reasoner, builder, memory_agent, consolidation)
  - `run_id`: UUID, ForeignKey → runs.id, nullable (null for cross-run memories created by consolidation)
  - `created_at`: DateTime, server_default=now
  - `updated_at`: DateTime, onupdate=now
  - `last_accessed_at`: DateTime, nullable
  - `access_count`: Integer, default=0
  - `importance`: Float, not null — 1.0 to 10.0 scale
  - `confidence`: Float, not null — 0.0 to 1.0 scale
  - `corroborations`: Integer, default=0
  - `contradictions`: Integer, default=0
  - `valid_from`: DateTime, not null, server_default=now
  - `valid_to`: DateTime, nullable — null means currently valid
  - `superseded_by`: UUID, ForeignKey → memories.id, nullable
  - `metadata_`: JSON (mapped as `metadata` in Python) — flexible key-value for source URLs, evidence pointers, etc.

- Indexes:
  - `ix_memories_namespace` on namespace
  - `ix_memories_run_id` on run_id
  - `ix_memories_source_stage` on source_stage
  - `ix_memories_confidence` on confidence
  - `ix_memories_valid_to` on valid_to (for filtering currently-valid memories)
  - Composite: `ix_memories_ns_confidence` on (namespace, confidence)

- Helper async functions in a new `shared/memories.py`:
  - `async create_memory(session, **kwargs) -> Memory`
  - `async get_memories(session, namespace=None, min_confidence=None, valid_only=True, limit=50) -> list[Memory]`
  - `async touch_memory(session, memory_id)` — update last_accessed_at, increment access_count
  - `async supersede_memory(session, old_id, new_content, **kwargs) -> Memory` — mark old as superseded, create new
  - `async update_confidence(session, memory_id, corroborate=False, contradict=False)` — increment counter, adjust confidence

## Acceptance Criteria
- [ ] AC1: `create_all()` creates the memories table alongside existing tables (Run, Model, Experiment, Artifact) without error
- [ ] AC2: Can create a Memory with all required fields, persist it, and query it back by namespace
- [ ] AC3: `get_memories(valid_only=True)` excludes memories where `valid_to` is not null
- [ ] AC4: `supersede_memory()` sets `valid_to=now` and `superseded_by` on the old memory, creates a new memory, and returns the new one
- [ ] AC5: `update_confidence(corroborate=True)` increments corroborations and increases confidence; `update_confidence(contradict=True)` increments contradictions and decreases confidence
- [ ] AC6: `touch_memory()` updates `last_accessed_at` and increments `access_count`

## Files Likely Affected
- `shared/shared/models.py` — add Memory model
- `shared/shared/memories.py` — new file, helper functions
- `shared/pyproject.toml` — no new dependencies (SQLAlchemy already present)

## Context
Phase spec: `docs/specs/knowledge/phase-1-infrastructure.md`
General spec: `docs/specs/knowledge/general.md`
Heat: `data-model`
Depends on P1-001 because both modify the `shared` package and schema init — sequential to avoid merge conflicts in `models.py`.
