# sim-recall — Phase Breakdown

> Status: current | Created: 2026-04-17 | Last updated: 2026-04-17
> References: [general.md](general.md)

## Phases

- [x] **Phase 1: Context Retrieval** — Expose `retrieve_context` tool in the Orchestrator wrapping Pablo's `retrieve_knowledge`. Wire Architect, Analyst, Reporter to consult the Knowledge Backbone before reasoning. Absorbs the old TODOs #2 (Analyst/Reporter) and #3 (Architect).
  - Dependencies: none (Pablo's retrieval stack already exists)
  - Issues: P1-001, P1-002, P1-003, P1-004
  - Heats: core (P1-001) → wiring (P1-002) ∥ prompts (P1-003) → tests (P1-004)

- [ ] **Phase 2: Chat History Persistence** — New `chat_messages` table + Alembic migration. Hook `Orchestrator.chat()` to persist turns behind `ENABLE_CHAT_PERSISTENCE` flag. Foundation for Phase 3's conversation-aware queries.
  - Dependencies: none
  - Estimated issues: ~3

- [ ] **Phase 3: NL→SQL History Query** — `query_history(question)` tool using Haiku for NL→SQL translation, sqlparse AST validation, SELECT-only whitelist over `experiments` + `models` + `memories` + `chat_messages`.
  - Dependencies: Phase 2 (needs `chat_messages` as queryable surface)
  - Estimated issues: ~5
