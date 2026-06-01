# sim-recall — Phase Breakdown

> Status: current | Created: 2026-04-17 | Last updated: 2026-05-11
> References: [general.md](general.md)

## Phases

- [x] **Phase 1: Context Retrieval** — Expose `retrieve_context` tool in the Orchestrator wrapping Pablo's `retrieve_knowledge`. Wire Architect, Analyst, Reporter to consult the Knowledge Backbone before reasoning. Absorbs the old TODOs #2 (Analyst/Reporter) and #3 (Architect).
  - Dependencies: none (Pablo's retrieval stack already exists)
  - Issues: P1-001, P1-002, P1-003, P1-004
  - Heats: core (P1-001) → wiring (P1-002) ∥ prompts (P1-003) → tests (P1-004)

- [x] **Phase 2: Chat History Persistence** — New `chat_messages` table + Alembic migration. Hook `Orchestrator.chat()` to persist turns behind `ENABLE_CHAT_PERSISTENCE` flag. Foundation for Phase 3's conversation-aware queries.
  - Dependencies: none
  - Issues: P2-001, P2-002, P2-003
  - Heats: chat-history (P2-001 → P2-002 → P2-003)
  - Spec: [phase-2-chat-persistence.md](phase-2-chat-persistence.md)

- [x] **Phase 3: NL→SQL History Query** — `query_history(question)` tool using Haiku for NL→SQL translation, sqlparse AST validation, SELECT-only whitelist over `experiments` + `models` + `memories` + `chat_messages`.
  - Dependencies: Phase 2 (needs `chat_messages` as queryable surface)
  - Issues: P3-001, P3-002, P3-003, P3-004
  - Heats: nlsql-core (P3-001 → P3-002) → orchestrator (P3-003) ∥ safety (P3-004)
  - Spec: [phase-3-nlsql-history.md](phase-3-nlsql-history.md)
