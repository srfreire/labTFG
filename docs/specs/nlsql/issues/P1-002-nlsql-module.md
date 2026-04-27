---
id: P1-002
title: Implement nlsql plan, execute, fetch, and synthesize pipeline
status: done
kind: strike
phase: 1
heat: foundation
blocked_by: [P1-001]
---

# P1-002: Implement nlsql plan, execute, fetch, and synthesize pipeline

## Objective

Complete the `nlsql.py` module with the full 5-step pipeline: plan (LLM),
validate, execute (Postgres), S3 fetch (conditional), synthesize (LLM).

## Requirements

### Public API

```python
async def query_experiments(question: str) -> str:
```

Returns a natural language answer in Spanish. Never raises — all errors
produce user-friendly messages.

### Step 1: Plan

LLM call with the schema prompt (static string from design.md) + user question.
Returns JSON:
```json
{"sql": "SELECT ...", "fetch_s3": ["analyst"], "reasoning": "..."}
```

Use `shared.settings.NLSQL_MODEL` for the model. Use the existing OpenRouter
client pattern from the codebase (check how other agents make LLM calls).

If LLM returns invalid JSON: return "No pude interpretar la pregunta. Intenta
reformularla."

### Step 2: Validate

Call `validate_sql()` from P1-001. If error, return descriptive message.

### Step 3: Execute

Run validated SQL in async Postgres session with `SET TRANSACTION READ ONLY`.
Use `shared.db` async session (follow existing pattern in orchestrator/tools).
Return results as list of dicts.

If execution fails: `logger.warning`, return "Error al ejecutar la consulta."
If zero results: return "No encontré experimentos que coincidan con tu búsqueda."

### Step 4: S3 Fetch (conditional)

If plan's `fetch_s3` is non-empty:
1. From SQL result rows, take first `settings.NLSQL_MAX_S3_FETCH` rows
2. For each row, fetch S3 keys in parallel (`asyncio.gather`)
3. Truncate each JSON to ~4000 chars
4. Failures: `logger.warning`, omit that entry

### Step 5: Synthesize

Second LLM call with: original question + SQL results as table + S3 data.
Returns natural language answer in Spanish.

### Schema prompt

Static string — copy from design.md section "Schema Prompt". Define as
module-level constant `_SCHEMA_PROMPT`.

## Acceptance Criteria

- [ ] `query_experiments(question)` returns NL answer string
- [ ] Plan step parses LLM JSON correctly
- [ ] Execute uses READ ONLY transaction
- [ ] S3 fetch respects `NLSQL_MAX_S3_FETCH` limit
- [ ] S3 fetch truncates content to ~4000 chars
- [ ] All error paths return user-friendly Spanish messages
- [ ] Never raises exceptions

## Files Likely Affected

- `phase2-juan/simlab/nlsql.py` — add plan, execute, fetch, synthesize functions
