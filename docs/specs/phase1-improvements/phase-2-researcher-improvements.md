# Phase 2: Mejoras Researcher/DeepResearcher

> Status: current | Created: 2026-04-10 | Last updated: 2026-04-11
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective
Mejorar la calidad y rigor académico del output del Researcher y DeepResearcher: nueva herramienta de búsqueda de papers (Semantic Scholar), secciones adicionales en deep reports, lista de papers consolidada, y cross-paradigm table reformateada.

## Requirements

### R1: Semantic Scholar API como tool
Nueva herramienta `search_papers` para el DeepResearcher que llama a `api.semanticscholar.org/graph/v1/paper/search`. Complementa `web_search` (no lo reemplaza). Devuelve título, autores, año, abstract, DOI, citation count. Rate limit: 1 req/seg.

### R2: Primary locus en deep reports
Añadir sección `## Primary Locus` al output format del DeepResearcher (`DEEP_RESEARCHER_SYSTEM_PROMPT`). Regiones cerebrales relevantes del paradigma.

### R3: Key concepts en deep reports
Añadir sección `## Key Concepts` al output format del DeepResearcher. Glosario breve de términos/conceptos que aparecen recurrentemente en los papers del paradigma.

### R4: Papers consolidados en report.md
El Researcher, al generar `report.md`, consolida en una sección `## References` todos los papers citados en todos los deep reports. No busca papers nuevos — agrega los existentes.

### R5: Cross-paradigm table reformateada
La cross-paradigm table pasa de listar zonas por paradigma a una matriz: filas = paradigmas, columnas = todas las zonas encontradas (de los `## Primary Locus`), celdas = ✓/✗.

## Acceptance Criteria
- [x] AC1: DeepResearcher tiene herramienta search_papers que consulta Semantic Scholar API
- [x] AC2: Deep reports contienen sección ## Primary Locus
- [x] AC3: Deep reports contienen sección ## Key Concepts
- [x] AC4: report.md contiene sección ## References con papers consolidados de todos los deep reports
- [x] AC5: Cross-paradigm table usa formato matriz zonas×paradigmas con ✓/✗
- [x] AC6: web_search y search_papers coexisten como herramientas del DeepResearcher

## Technical Notes
- DeepResearcher prompt en `deep_researcher.py:15`
- Researcher prompt en `researcher.py:22`
- `save_summary_report()` en `tools/reports.py:55` guarda report.md
- El Researcher genera report.md como texto libre del LLM — las instrucciones de formato van en el system prompt
- Semantic Scholar API no requiere API key para uso básico

## Decisions
- Semantic Scholar complementa web_search, no lo reemplaza
- Cross-paradigm table con ✓/✗ la genera el LLM del Researcher siguiendo instrucciones de formato en el prompt
- Papers consolidados: el Researcher lee los deep reports y agrega las secciones ## References
