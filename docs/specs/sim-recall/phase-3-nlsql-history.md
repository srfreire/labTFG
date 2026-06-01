# Phase 3: NL→SQL History Query

> Status: done | Created: 2026-05-11 | Last updated: 2026-05-11 (P3-001..P3-004 done)
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Give the Orchestrator a `query_history(question)` tool that translates
natural-language questions into safe SELECT queries over the user's
experiments, models, memories, and chat history, returning a compact
markdown result back to the chat.

## Requirements

### R1 — Reuse `simlab/nlsql.py` primitives

The existing module already provides:

- `validate_sql()` — `sqlparse`-based SELECT-only, table whitelist,
  LIMIT enforcement.
- `_plan(question)` — Haiku NL→SQL translation.
- `_execute(sql, db)` — runs the SQL with timeout.

Phase 3 extends and adds; it does not duplicate these primitives.

### R2 — Extend table whitelist

Add `chat_messages` and `memories` to `_ALLOWED_TABLES`. Update the
Haiku system prompt inside `_plan()` to describe these two tables
(columns, semantics, join keys to `experiments`).

The whitelist after Phase 3:
`{experiments, models, runs, simulation_observations, memories, chat_messages}`.

### R3 — `query_history()` entry point

New function in `simlab/nlsql.py`:

```python
async def query_history(
    question: str,
    *,
    db: DatabaseService,
) -> str:
    """NL→SQL light path for the Orchestrator.
    Plan → validate → execute → markdown table. No S3, no synthesis.
    Returns a chat-ready markdown string.
    """
```

Behaviour:

- Calls `_plan(question)` → SQL or `{"error": "out_of_scope", ...}`.
- On out-of-scope: return a short markdown sentence
  (e.g. `> No puedo responder eso con SQL — la consulta está fuera del alcance de query_history.`).
- Calls `validate_sql()`. On rejection: log + return a markdown error
  message (no stack, just the validator's reason string).
- Calls `_execute()` with `db`. Catch any exception, log, return
  graceful markdown message.
- Format rows as a markdown table. Header row from `rows[0].keys()`.
  Empty rows → `> Sin resultados.` Truncated (`len(rows) == _MAX_LIMIT`) → append
  `\n_Mostrando primeras 50 filas._`.

### R4 — Settings flag

Add `ENABLE_QUERY_HISTORY: bool = False` to `shared/shared/settings.py`,
parallel to `ENABLE_KNOWLEDGE_READ` and `ENABLE_CHAT_PERSISTENCE`.

### R5 — Wire as Orchestrator tool

- New `QUERY_HISTORY_TOOL` schema in `simlab/orchestrator.py`.
- Inside `Orchestrator._build_tools()`, when `settings.ENABLE_QUERY_HISTORY`
  is true, register `query_history` and append the schema.
- Append a short section to the Orchestrator system prompt with usage
  examples (mirroring how the KG retrieve_context section is added today).

### R6 — Safety and e2e tests

- Unit: validator rejects every `INSERT`/`UPDATE`/`DELETE`/`DROP`/
  `CREATE`/`ALTER`.
- Unit: validator rejects queries touching tables outside the whitelist
  (e.g. `pg_user`, `nodes`).
- Unit: validator injects default `LIMIT 50` when absent; caps explicit
  `LIMIT > 500` to 50 (current behaviour).
- Integration: seed a test DB with experiments + chat_messages + memories,
  run `query_history` over each, verify markdown table comes back.
- Integration: an out-of-scope question ("¿qué hora es?") returns the
  out-of-scope markdown and does not call `_execute`.
- Integration: flag OFF → tool not in Orchestrator's tool list.

## Acceptance Criteria

- [x] AC1: `_ALLOWED_TABLES` includes `chat_messages` and
      `pipeline_memories`; a SELECT touching either passes
      `validate_sql` if otherwise legal. (Spec mentioned `memories`
      — the live schema split it into `pipeline_memories` +
      `simulation_observations`; both are whitelisted.)
- [x] AC2: `query_history` end-to-end against test DB returns a markdown
      table for a question that maps to a SELECT.
- [x] AC3: `query_history` returns the out-of-scope markdown when Haiku
      flags the question as such, without calling `_execute`.
- [x] AC4: With `ENABLE_QUERY_HISTORY=False`, the Orchestrator's tool
      list does not contain `query_history`.
- [x] AC5: With flag on, the Orchestrator's `chat()` can invoke
      `query_history` and the markdown is returned to the user.
- [x] AC6: Every disallowed SQL verb (INSERT/UPDATE/DELETE/DROP/CREATE/
      ALTER) is rejected by `validate_sql`.

## Technical Notes

- `_plan()` currently lives in `nlsql.py` with a hand-written prompt; the
  schema docs for `chat_messages` and `memories` go inside that same
  prompt string — no separate config.
- `query_history` is *lighter* than the existing `query_experiments`:
  no `_fetch_s3`, no `_synthesize` LLM call. The markdown formatter is
  new.
- Tool wiring goes inside `_build_tools()` in `orchestrator.py`, near
  the other conditional sections (recall, knowledge).
- Orchestrator system prompt extension follows the pattern of the
  existing `_KNOWLEDGE_RETRIEVAL_PROMPT_SECTION`.
- Test DB fixtures: reuse whatever pattern the existing `tests/recall/`
  and `tests/test_nlsql*.py` files use.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Reuse vs duplicate primitives | Reuse `validate_sql` + `_plan` + `_execute` from `nlsql.py` | Less code; phase scope is "expose new tool", not "rewrite NL→SQL". |
| Tool weight | Light path — no S3, no synthesis | `query_history` is for fast chat lookups; the heavyweight `query_experiments` stays for the Analyst. |
| Markdown formatter | Inline in `query_history`, not a shared util | Format is specific to chat; no other consumer. |
| Out-of-scope UX | Markdown sentence, no error block | Friendlier than `{"error": ...}` JSON in chat. |
| Flag default | `False` | Match `ENABLE_KNOWLEDGE_*` / `ENABLE_CHAT_PERSISTENCE`. |
| Schema doc location | Inline in `_plan()` system prompt | Single source; no separate schema config file. |
