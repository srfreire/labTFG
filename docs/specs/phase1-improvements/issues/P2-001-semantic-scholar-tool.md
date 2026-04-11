---
id: P2-001
title: Semantic Scholar API tool para DeepResearcher
status: done
kind: strike
phase: 2
heat: search-tool
priority: 1
blocked_by: []
created: 2026-04-10
updated: 2026-04-11
---

# P2-001: Semantic Scholar API tool para DeepResearcher

## Objective
Crear una nueva herramienta `search_papers` que consulte la API de Semantic Scholar y añadirla al DeepResearcher junto a `web_search`.

## Requirements
- Nuevo archivo `tools/papers.py` con:
  - `SEARCH_PAPERS_SCHEMA` — tool schema para Claude (name, description, input_schema con `query: str` y `limit: int` opcional)
  - `create_search_papers()` — factory que devuelve async callable
  - Llama a `GET https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit={limit}&fields=title,authors,year,abstract,externalIds,citationCount`
  - Devuelve resultados formateados como texto: título, autores, año, DOI, abstract, citation count
  - Rate limit: 1 req/seg (simple sleep entre requests)
  - Sin API key (uso básico)
  - Manejo de errores: si la API falla, devolver mensaje claro en vez de crashear
- Añadir `search_papers` a `DeepResearcher.tools` y `DeepResearcher.registry`
- Actualizar `DEEP_RESEARCHER_SYSTEM_PROMPT` para instruir al agente a usar ambas herramientas:
  - `search_papers` para encontrar papers académicos verificados
  - `web_search` para contexto general y descubrimiento amplio

## Acceptance Criteria
- [x] Existe `tools/papers.py` con SEARCH_PAPERS_SCHEMA y create_search_papers
- [x] search_papers consulta Semantic Scholar API y devuelve papers con DOI
- [x] DeepResearcher tiene web_search y search_papers como herramientas
- [x] Rate limit de 1 req/seg implementado
- [x] Errores de API se manejan sin crashear

## Files Likely Affected
- `src/decisionlab/tools/papers.py` — nuevo archivo
- `src/decisionlab/agents/deep_researcher.py` — añadir tool + actualizar prompt

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `search-tool`

## Completion Summary

**Commit:** `363e651` — `feat[tools]: Semantic Scholar API tool for DeepResearcher (P2-001)`

### What was built
- `search_papers` tool: queries Semantic Scholar API, returns formatted papers with title, authors, year, DOI, abstract, citation count
- Async rate limiter with `asyncio.Lock` — 1 req/s, safe under concurrent dispatch
- 429 retry: detects rate-limit responses, waits `Retry-After`, retries once
- Malformed JSON guard: handles non-JSON 200 responses gracefully
- DeepResearcher prompt updated to instruct dual-tool usage (search_papers first, web_search to fill gaps)
- `max_iterations` bumped 5 → 7 to accommodate up to 5 combined searches

### Files created/modified
- `src/decisionlab/tools/papers.py` — new: schema + factory with rate limiter, 429 retry, error handling
- `src/decisionlab/agents/deep_researcher.py` — modified: added search_papers to tools/registry, updated system prompt
- `tests/tools/test_papers.py` — new: 9 tests (schema, success, errors, 429 retry, malformed JSON, empty results, network error)
- `tests/agents/test_deep_researcher.py` — modified: 3 new tests (tool list, registry, prompt mentions both tools)

### Decisions
- Rate limiter uses `asyncio.Lock` inside closure (per-instance, not global) to prevent race conditions under concurrent dispatch
- 429 retry limited to one attempt to avoid infinite loops
- `max_iterations` increased to 7 (5 searches + text generation turns)
