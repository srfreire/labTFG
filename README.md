# DecisionLab

Laboratorio virtual para simulacion y analisis de paradigmas de toma de decisiones humanas mediante agentes inteligentes.

|  |  |
| --- | --- |
| **Autores** | Juan Freire Alvarez, Pablo Pazos Parada |
| **Tutor** | Eduardo Manuel Sanchez Vila |

---

## Que es esto

Un sistema multi-agente que investiga paradigmas de toma de decisiones (homeostatico, hedonico, prospect theory...), los implementa como agentes autonomos en Python, los ejecuta en un entorno de simulacion compartido y genera informes comparativos de su comportamiento.

El proyecto se divide en dos fases complementarias:

### Fase 1 — Modelado de agentes (Pablo)

Pipeline de 3 agentes LLM que, dado un problema de toma de decisiones, produce N agentes autonomos (codigo Python) listos para simular:

```
Usuario: "comportamiento alimentario"
    → Researcher (busca paradigmas en literatura cientifica)
    → Reasoner (formaliza postulados como pseudocodigo/reglas)
    → Builder (implementa DecisionModel .py + tests)
```

### Fase 2 — Infraestructura de simulacion (Juan)

Plataforma para ejecutar, observar, analizar y documentar el comportamiento de los agentes:

```
DecisionModels (Fase 1)
    → Architect (configura environment)
    → Tracker (registra eventos y trayectorias)
    → Analyst (identifica patrones)
    → Reporter (genera informes)
```

---

## Estructura del repositorio

```
phase1-pablo/                          — Fase 1: pipeline de modelado
  src/decisionlab/                     — Paquete principal
    models/protocol.py                 — Protocol DecisionModel, Action, Perception
    agents/                            — Researcher, Reasoner, Builder (placeholder)
    tools/                             — web_search, semantic_scholar, file_io, code_runner
    router.py                          — Orquestador del pipeline
    cli.py                             — Punto de entrada CLI
  examples/denis/                      — Modelos de ejemplo (del paper de referencia)
    homeostatic.py                     — Modelo homeostatico (EDOs fisiologicas)
    hedonic.py                         — Modelo hedonico (Q-Learning)
    integrated.py                      — Modelo integrado (4 modos de combinacion)
  tests/                               — Tests unitarios e integracion

phase2-juan/                           — Fase 2: laboratorio virtual
  simlab/                              — Paquete principal
    environment.py                     — Environment, Agent, Resource, Event, ModelAdapter
    spec.py                            — Validacion y conversion de JSON specs
    architect.py                       — Architect agent (genera specs de environment)
    tracker.py                         — Tracker agent (observa simulaciones)
    analyst.py                         — Analyst agent (identifica patrones)
    reporter.py                        — Reporter agent (genera informes PDF)
    tools.py                           — Tools compartidas (simulation data access)
    utils.py                           — Utilidades compartidas
    runtime/                           — Loop agentico y dispatcher de tools
    templates/                         — Plantilla LaTeX para informes
  tests/                               — Tests unitarios e integracion
  docs/DESIGN.md                       — Diseno de la arquitectura

docs/                                  — Documentos de referencia
  TFM_v_FINAL.pdf                      — Paper de referencia (TFM Denis)
  RESUMEN_TFM_Denis.md                 — Resumen del paper de referencia
  survival_metabolicModel_behave_clean_Denis.py  — Script de ejemplo del paper
```

---

## Punto de integracion

Las dos fases se conectan a traves del **Protocol** `DecisionModel` — una interfaz con tres metodos: `decide()`, `update()` y `get_state()`.

La Fase 1 implementa modelos concretos con tipos propios (percepciones tipadas como dataclass). La Fase 2 define un Protocol generico con percepciones como `dict`. Un **adaptador** (`ModelAdapter`) traduce entre ambos, permitiendo que el Environment ejecute cualquier paradigma sin depender del codigo de la Fase 1.

---

## Setup

Requiere Python 3.12+ y [uv](https://docs.astral.sh/uv/).

```bash
# Fase 1
cd phase1-pablo
uv sync

# Fase 2
cd phase2-juan
uv sync
```

## Tests

```bash
# Fase 2 (incluye tests del adapter con modelos de Fase 1)
cd phase2-juan
uv run pytest tests/ -v

# Fase 1
cd phase1-pablo
uv run pytest tests/ -v
```

## Script de referencia

```bash
python docs/survival_metabolicModel_behave_clean_Denis.py
```

Requiere `tkinter`, `matplotlib`, `numpy`.

---

## Stack tecnico

| Componente | Tecnologia |
| --- | --- |
| Lenguaje | Python (uv) |
| LLM | Claude (Anthropic) |
| SDK agentes | anthropic (API directa con tool use loop) |
| Interfaz | CLI (rich/typer) — solo Fase 1 por ahora |
| Tests | pytest |
| Datos | JSON (SQLite previsto) |
| Informes | LaTeX (tectonic) → PDF |
