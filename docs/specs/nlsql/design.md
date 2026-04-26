# NLSQL: Natural Language to SQL Experiment Queries

## Overview

A natural language query tool for the experiment database. Users ask questions
in the Orchestrator chat ("what reward did agents get in my last 3 prospect
theory experiments?") and the tool translates to SQL, executes against
Postgres, optionally fetches rich data from S3, and synthesizes a natural
language answer.

## Motivation

The experiment database holds metadata (status, models, steps, timestamps) in
Postgres and rich results (analyst patterns, tracker trajectories, events) in
S3 as JSON files. Today there is no way to search across experiments — the
Orchestrator has `list_experiments` (returns last N) but nothing for filtered
queries or cross-experiment analysis. NLSQL fills that gap.

## Architecture

```
User (via chat) → Orchestrator → query_experiments tool
                                      │
                                      ▼
                               nlsql.py module
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                    1. Plan LLM   2. Validate  3. Execute
                    (question →   (sqlparse,   (async pg
                     SQL + S3     SELECT only,  session,
                     plan)        allowed       READ ONLY)
                                  tables,
                                  LIMIT cap)
                                      │
                                      ▼
                              4. S3 fetch (conditional)
                                  asyncio.gather of keys
                                  limited to NLSQL_MAX_S3_FETCH
                                      │
                                      ▼
                              5. Synthesize LLM
                                  (SQL results + S3 data → NL answer)
```

### Step 1: Plan

An LLM call (model configurable via `NLSQL_MODEL`, default Haiku) receives:
- The database schema description (static string, 3 tables)
- The user's natural language question

Returns a structured JSON plan:
```json
{
  "sql": "SELECT id, description, s3_analyst_key FROM experiments WHERE ...",
  "fetch_s3": ["analyst"],
  "reasoning": "Need analyst output to find patterns"
}
```

`fetch_s3` is a list of S3 content types: `["analyst", "events", "tracker",
"replay"]`. Each maps to the column `s3_<type>_key` on the experiment row.
If `null` or `[]`, no S3 fetch is performed.

### Step 2: Validate

Static validation of the generated SQL before execution:

1. `sqlparse.parse()` — must produce exactly 1 statement
2. Statement type must be `SELECT` (reject INSERT/UPDATE/DELETE/DROP/ALTER)
3. Referenced tables must be in allowlist: `{experiments, models, runs}`
4. If no `LIMIT` clause, append `LIMIT 50`
5. If `LIMIT > 50`, rewrite to `LIMIT 50`

If validation fails, return a descriptive error to the user without executing.

### Step 3: Execute

Run the validated SQL in an async Postgres session with
`SET TRANSACTION READ ONLY` as an additional safety net.

Return results as a list of dicts (column name → value).

### Step 4: S3 Fetch (conditional)

If the plan's `fetch_s3` is non-empty:

1. From the SQL result rows, take the first `NLSQL_MAX_S3_FETCH` rows
   (ordered by `created_at DESC`)
2. For each row, fetch the indicated S3 keys in parallel (`asyncio.gather`)
3. If a fetch fails: `logger.warning`, omit that entry (resilient, never blocks)
4. Truncate each JSON to ~4000 characters to avoid saturating the synthesize
   context
5. If SQL returned more rows than the limit, note it for the synthesize step

### Step 5: Synthesize

Second LLM call (same model as plan) receives:
- Original user question
- SQL results as a formatted table
- S3 data (if fetched), truncated
- Note if results were capped

Returns: natural language answer in Spanish with concrete data (numbers, agent
names, patterns). If no results: "No encontré experimentos que coincidan con
tu búsqueda."

## Schema Prompt

Static string describing the queryable tables:

```
Tables available for querying:

experiments(id UUID PK, created_at TIMESTAMP, updated_at TIMESTAMP,
  description TEXT, status VARCHAR(50), spec JSONB, models_used JSONB,
  steps INT, seed INT, s3_events_key VARCHAR, s3_replay_key VARCHAR,
  s3_tracker_key VARCHAR, s3_analyst_key VARCHAR, s3_pdf_key VARCHAR,
  s3_tex_key VARCHAR, s3_charts_prefix VARCHAR)

  status lifecycle: created → simulated → tracked → analyzed → reported
  models_used: JSON array of model keys e.g. ["prospect-theory/cumulative-pt"]
  spec: JSON with grid_width, grid_height, actions, resources, effects

models(id UUID PK, class_name VARCHAR, paradigm VARCHAR NOT NULL,
  formulation VARCHAR NOT NULL, description TEXT, run_id UUID FK→runs,
  s3_model_key VARCHAR, registered_at TIMESTAMP, metadata JSONB)

  UNIQUE(run_id, paradigm, formulation)

runs(id UUID PK, created_at TIMESTAMP, problem_description TEXT NOT NULL,
  status VARCHAR(50), s3_report_key VARCHAR, s3_prefix VARCHAR NOT NULL,
  artifact_count INT)
```

Tables NOT exposed: `memories`, `artifacts` (not useful for experiment queries).

## Orchestrator Integration

### Tool schema

```json
{
  "name": "query_experiments",
  "description": "Query the experiment database using natural language. Answers questions about past experiments, models, results, patterns, and cross-experiment comparisons.",
  "input_schema": {
    "type": "object",
    "properties": {
      "question": {
        "type": "string",
        "description": "Natural language question about experiments"
      }
    },
    "required": ["question"]
  }
}
```

### Wiring

Added to `ALL_TOOLS` in the orchestrator. The closure in `_build_tools`
calls `nlsql.query_experiments(params["question"])`.

### System prompt addition

```
8. **query_experiments** — queries the experiment database with natural language.
   Use when the user asks about past experiments, comparisons between runs,
   historical results, or anything that requires searching experiment data.
```

## Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `NLSQL_MAX_S3_FETCH` | int | 3 | Max experiment rows to fetch S3 data for per query |
| `NLSQL_MODEL` | str | `"anthropic/claude-haiku-4-5"` | Model for plan + synthesize LLM calls |

Both in `shared/shared/settings.py`, overridable via environment variables.

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Plan LLM returns invalid JSON | Return "No pude interpretar la pregunta. Intenta reformularla." |
| SQL validation fails | Return descriptive error: "Query inválida: solo se permiten SELECT sobre experiments, models, runs." |
| SQL execution fails | `logger.warning`, return "Error al ejecutar la consulta." |
| S3 fetch fails (partial) | Warning, omit that row's S3 data, continue with rest |
| S3 fetch fails (total) | Warning, synthesize with SQL-only data |
| Zero SQL results | Return "No encontré experimentos que coincidan con tu búsqueda." |

## Testing

### Unit tests
- `test_validate_select_only` — rejects INSERT/UPDATE/DELETE
- `test_validate_allowed_tables` — rejects queries on memories/artifacts
- `test_validate_limit_enforced` — adds LIMIT 50 if missing, caps if > 50
- `test_plan_parsing` — mock LLM, verify JSON plan extraction
- `test_s3_fetch_respects_limit` — only fetches NLSQL_MAX_S3_FETCH rows
- `test_s3_fetch_partial_failure` — one fetch fails, others succeed
- `test_synthesize_no_s3` — metadata-only question, no S3 fetch

### Integration test
- `test_query_experiments_roundtrip` — mock LLM + mock S3, full pipeline from question to NL answer

## Files to create/modify

| File | Change |
|------|--------|
| `phase2-juan/simlab/nlsql.py` | New module: plan, validate, execute, fetch, synthesize |
| `phase2-juan/simlab/orchestrator.py` | Add `query_experiments` tool schema + closure in `_build_tools` + system prompt line |
| `shared/shared/settings.py` | Add `NLSQL_MAX_S3_FETCH` and `NLSQL_MODEL` |
| `phase2-juan/tests/test_nlsql.py` | New test file |

## Out of Scope

- REST endpoint for NLSQL (future: extract to `POST /api/query` when frontend has search UI)
- Querying the Knowledge Graph / memories table (already covered by `retrieve_context`)
- Write operations (INSERT/UPDATE) — this is strictly read-only
- Caching of query results
