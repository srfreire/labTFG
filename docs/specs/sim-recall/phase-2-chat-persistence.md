# Phase 2: Chat History Persistence

> Status: done | Created: 2026-05-11 | Last updated: 2026-05-11 (P2-001..P2-003 done)
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Persist every Orchestrator conversation turn into a new `chat_messages`
table, behind a feature flag, so Phase 3's `query_history` tool has a
queryable surface for "what did I ask about X?" style questions.

## Requirements

### R1 — `chat_messages` table

Create the table exactly as specified in `general.md`:

```sql
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  experiment_id UUID NULL REFERENCES experiments(id) ON DELETE SET NULL,
  role VARCHAR(20) NOT NULL,
  content TEXT NOT NULL,
  tool_name VARCHAR(50) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_chat_messages_session ON chat_messages(session_id);
CREATE INDEX ix_chat_messages_experiment ON chat_messages(experiment_id);
CREATE INDEX ix_chat_messages_created ON chat_messages(created_at);
```

`role` accepted values (no DB-level check constraint to keep flexibility,
enforced in writer): `user`, `assistant`, `tool_use`, `tool_result`.

### R2 — Settings flag

Add `ENABLE_CHAT_PERSISTENCE: bool = False` to `shared/shared/settings.py`,
following the pattern of `ENABLE_KNOWLEDGE_READ` / `ENABLE_KNOWLEDGE_WRITE`.

### R3 — Block → row serializer

A pure function that takes an Anthropic message dict (one entry of
`Orchestrator._messages`) plus the active `session_id` and
`experiment_id`, and returns a list of `chat_messages` row dicts.

Mapping rules:

- `{"role": "user", "content": str}` → one row, `role='user'`, `content=str`.
- `{"role": "user", "content": [tool_result blocks...]}` → one row per
  block, `role='tool_result'`, `content=json.dumps(block.content)`,
  `tool_name=block.tool_use_id_lookup` (resolved by caller; the writer
  itself only sees the block).
- `{"role": "assistant", "content": [blocks...]}` →
  - each `text` block → one row, `role='assistant'`,
    `content=block.text`.
  - each `tool_use` block → one row, `role='tool_use'`,
    `content=json.dumps({"name": block.name, "input": block.input})`,
    `tool_name=block.name`.

The serializer is **pure**: no DB access, no I/O. Receives data, returns
row dicts.

### R4 — Bulk persistence

A writer function `persist_turn(session, rows)` that does a single
`INSERT INTO chat_messages` for the row list. Uses
`session.execute(insert(ChatMessage).values(rows))` — one round-trip even
for 60+ rows. Caller wraps in `try/except`: any failure logs a warning
and returns; **never** raises into `chat()`.

### R5 — Orchestrator wiring

- `Orchestrator.__init__` generates `self._session_id = uuid.uuid4()`.
- `Orchestrator.chat()`, after the existing `self._messages.append(...)`
  calls, if `settings.ENABLE_CHAT_PERSISTENCE` is true:
  - Collects the **new** messages added in this turn (the user input
    plus the assistant `response.content`).
  - Runs them through the serializer.
  - Bulk-inserts via the writer.
  - Snapshots `experiment_id` from `self._state.get("experiment_id")` at
    write time (NULL if none).
- Flag OFF → zero behavior change.

## Acceptance Criteria

- [x] AC1: Migration applies cleanly on a fresh DB and is reversible
      (downgrade drops the table + indexes).
- [x] AC2: `ENABLE_CHAT_PERSISTENCE=False` → `chat_messages` row count
      stays at 0 after multi-turn integration test.
- [x] AC3: `ENABLE_CHAT_PERSISTENCE=True` → after a simulated turn with
      user input, one `text` block, and two `tool_use` blocks, exactly
      4 rows exist for the same `session_id`, with the expected `role`
      values.
- [x] AC4: All rows from the same Orchestrator instance share one
      `session_id`. A second Orchestrator gets a distinct one.
- [x] AC5: Forcing a DB error during persist (mock raises) does not
      raise into `chat()`; the user-facing response still returns. A
      warning is logged.
- [x] AC6: If an experiment is active (`state["experiment_id"]` set),
      new rows for subsequent turns carry that `experiment_id`.

## Technical Notes

- ORM model lives in `shared/shared/models.py`, alongside `Run`, `Model`,
  `Experiment`, `Memory`. New `ChatMessage` class.
- Migration file goes under `shared/migrations/versions/` following the
  hashed-prefix naming of the existing migrations
  (e.g. `bfb1033cc32f_add_memories_table.py` as a template).
- Writer module lives at `phase2-juan/simlab/recall/chat_history.py`
  (paralelo a `simlab/knowledge/writer.py`).
- The serializer must handle the Anthropic SDK block objects (they have
  `.type`, `.text`, `.name`, `.input` attributes). See
  `Orchestrator._build_interaction_summary` for an existing example of
  iterating blocks.
- Use `sqlalchemy.dialects.postgresql.insert` if `ON CONFLICT` is ever
  needed; for v1 plain insert is fine.
- Logging via `logger = logging.getLogger(__name__)` already wired in
  orchestrator.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Insert timing | Bulk at end of `chat()` turn | 1 round-trip vs N; no background-task complexity. |
| Failure mode | Log + swallow | Persistence must never break the chat. |
| Session id resumption | None in Phase 2 | Out of scope; Phase 3 can add if needed. |
| Tool result row role | `tool_result` | Distinct from `assistant` so NL→SQL can filter. |
| Tool use row role | `tool_use` | Same reasoning. Different from spec's hint of "assistant" — clearer. |
| Granularity | 1 row per block | Matches `general.md`; better Phase 3 query surface. |
| Default flag | `False` | Match `ENABLE_KNOWLEDGE_*` convention. |
| ChatMessage in `shared.models` | yes | Aligned with `Experiment`, `Memory`, etc. |
