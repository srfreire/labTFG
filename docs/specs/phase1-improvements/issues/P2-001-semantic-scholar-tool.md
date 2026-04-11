---
id: P2-001
title: Semantic Scholar API tool para DeepResearcher
status: in-progress
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
- [ ] Existe `tools/papers.py` con SEARCH_PAPERS_SCHEMA y create_search_papers
- [ ] search_papers consulta Semantic Scholar API y devuelve papers con DOI
- [ ] DeepResearcher tiene web_search y search_papers como herramientas
- [ ] Rate limit de 1 req/seg implementado
- [ ] Errores de API se manejan sin crashear

## Files Likely Affected
- `src/decisionlab/tools/papers.py` — nuevo archivo
- `src/decisionlab/agents/deep_researcher.py` — añadir tool + actualizar prompt

## Context
Phase spec: `docs/specs/phase1-improvements/phase-2-researcher-improvements.md`
General spec: `docs/specs/phase1-improvements/general.md`
Heat: `search-tool`
