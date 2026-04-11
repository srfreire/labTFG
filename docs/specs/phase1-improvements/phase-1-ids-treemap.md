# Phase 1: Sistema de IDs y Tree Map

> Status: current | Created: 2026-04-10 | Last updated: 2026-04-10
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective
Implementar un sistema de IDs programáticos jerárquicos (T-P-F) en PipelineState que se propague a todos los agentes del pipeline, y generar un tree map en report.md con la jerarquía completa.

## Requirements

### R1: ID Registry en PipelineState
Añadir a `PipelineState` un registry que asigne IDs automáticos:
- `topic_counter: int` — contador de topics (normalmente 1 por run)
- `paradigm_counter: int` — contador global de paradigmas
- `id_registry: dict` — mapeo `{slug: ID}` para paradigmas y formulaciones
- Formato: `T01`, `T01-P01`, `T01-P01-F01` — 2 dígitos, secuencial
- IDs se asignan en orden de descubrimiento (Researcher para paradigmas, Formalizer para formulaciones)
- Persistidos en `pipeline_state.json`

### R2: Asignación de IDs en Researcher
Cuando el Researcher descubre paradigmas, el Router asigna `T01-P01`, `T01-P02`, etc. programáticamente (no el LLM). El topic ID `T01` se asigna al inicio del run.

### R3: Asignación de IDs en Formalizer
Cuando el Formalizer genera formulaciones, el Router asigna `T01-P01-F01`, `T01-P01-F02`, etc. El ID se parsea del heading `## Formulation N:` del .md generado.

### R4: Propagación de IDs downstream
Reasoner y Builder reciben y usan los IDs del registry en vez de construir `formulation_id` ad-hoc. Los archivos de salida usan el ID: `reasoner/T01-P01-F01.json`, `builder/T01-P01-F01_model.py`.

### R5: Tree map en report.md
Después del Formalizer (stage REVIEW_FORMALIZE), generar e insertar en `report.md` un tree map Markdown con la jerarquía T→P→F y sus IDs. Ejemplo:
```
T01: Food Decision-Making
├── T01-P01: Homeostatic Regulation
│   ├── T01-P01-F01: PI Controller
│   └── T01-P01-F02: Dual-Process Model
└── T01-P02: Hedonic Reward
    └── T01-P02-F01: Temporal Difference
```
Generado por código (no por LLM) leyendo el registry.

## Acceptance Criteria
- [x] AC1: PipelineState tiene id_registry que persiste en pipeline_state.json
- [x] AC2: Paradigmas reciben IDs `T{NN}-P{NN}` automáticamente al ser descubiertos
- [x] AC3: Formulaciones reciben IDs `T{NN}-P{NN}-F{NN}` automáticamente al ser generadas
- [ ] AC4: Archivos del Reasoner y Builder usan el ID del registry como nombre
- [ ] AC5: report.md contiene tree map generado programáticamente después del Formalizer
- [ ] AC6: Runs existentes sin IDs no crashean (backward compatible)

## Technical Notes
- `PipelineState` está en `router.py:52` — extender dataclass + save/load
- `slugify()` en `tools/reports.py:24` sigue existiendo para nombres de archivo legibles
- El Researcher no parsea paradigmas a objetos (`TODO` en `researcher.py:112`) — este issue necesita resolver eso para poder asignar IDs
- `selected_formulations` en PipelineState usa `{slug: [int]}` — migrar a usar IDs
- Regex para parsear formulations: `^##\s+Formulation\s+(\d+)\s*:\s*(.+)$` (usado en feedback.py)

## Decisions
- IDs son programáticos, no LLM-generated — determinismo
- El topic ID es siempre T01 por run (un run = un topic)
- El tree map se regenera cada vez que se añaden formulaciones
