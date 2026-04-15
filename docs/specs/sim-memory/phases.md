# sim-memory — Phase Breakdown

> Status: current | Created: 2026-04-15 | Last updated: 2026-04-15
> References: [general.md](general.md)

## Phases

- [x] **Phase 1: Core Writer** — Lógica pura del `TrackerMemoryWriter`: parsing del JSON del Tracker, filtrado de episodes, generación de facts en inglés, embedding + upsert a Postgres/Qdrant. Sin tocar el orchestrator. Testable en aislamiento con mocks.
  - Dependencies: none
  - Issues: P1-001, P1-002, P1-003, P1-004
  - Heats: writer (P1-001→P1-002→P1-003→P1-004, fully sequential)

- [x] **Phase 2: Integration** — Wiring del writer al flujo real: flag `ENABLE_KNOWLEDGE_WRITE`, invocación tras `observe_simulation` en el orchestrator, graceful degradation e integration test con docker-compose.
  - Dependencies: Phase 1
  - Issues: P2-001, P2-002, P2-003
  - Heats: integration (P2-001→P2-002→P2-003, fully sequential)
