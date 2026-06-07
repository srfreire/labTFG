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

Pipeline agentico coordinado por un Router que, dado un problema de toma de
decisiones, produce N agentes autonomos (codigo Python) listos para simular:

```
Usuario: "comportamiento alimentario"
    → Classifier (ancla el problema a un paradigma canonico cuando existe)
    → Researcher (busca paradigmas en literatura cientifica)
    → Formalizer (convierte informes en formulaciones matematicas)
    → Env spec (entrada humana / Fase 2)
    → Reasoner (adapta formulaciones al entorno como specs JSON)
    → Builder (implementa DecisionModel .py + tests)
```

Despues de cada revision humana, un **MemoryAgent** puede escribir el output
aceptado en el **Knowledge Backbone** (Neo4j + Qdrant + Postgres). Ese backbone
persiste paradigmas, formulaciones, specs, modelos y memorias entre runs, y
nutre a los agentes con contexto relevante via retrieval hibrido (KG traversal +
dense + sparse + RRF + reranking + CRAG).

### Fase 2 — Infraestructura de simulacion (Juan)

Plataforma para ejecutar, observar, analizar y documentar el comportamiento de los agentes:

```
DecisionModels (Fase 1)
    → Architect (configura environment)
    → Tracker (registra eventos y trayectorias)
    → Analyst (identifica patrones)
    → Reporter (genera informes PDF via LaTeX)
```

Coordinados por un **Orchestrator** con chat interactivo. Los agentes consultan el Knowledge Backbone (`retrieve_context`) para contrastar patrones observados contra postulados conocidos, y persisten observaciones de simulacion como memorias re-utilizables en runs futuros.

---

## Estructura del repositorio

```
phase1-pablo/                          — Fase 1: pipeline de modelado
  src/decisionlab/
    agents/                            — Classifier, Researcher, Formalizer, Reasoner, Builder, MemoryAgent
    knowledge/                         — Memory Agent, KG extraction, 3-layer retrieval, CRAG
    models/                            — Protocol DecisionModel, Action, Perception
    tools/                             — web_search, semantic_scholar, file_io, code_runner
    runtime/                           — Loop agentico y dispatcher de tools
    router.py                          — Orquestador del pipeline
    cli.py                             — Punto de entrada CLI
  docs/formal-documentation/            — Documentacion tecnica actual de Fase 1
  evals/                               — Suite de evaluacion (latencia, calidad retrieval)
  tests/                               — Tests unitarios e integracion

phase2-juan/                           — Fase 2: laboratorio virtual
  simlab/
    environment.py                     — Environment, Agent, Resource, Event
    spec.py                            — Validacion y conversion de JSON specs
    architect.py                       — Architect agent (genera specs de environment)
    tracker.py                         — Tracker agent (observa simulaciones)
    analyst.py                         — Analyst agent (identifica patrones)
    reporter.py                        — Reporter agent (genera informes PDF)
    orchestrator.py                    — Pipeline coordinator + chat interactivo
    model_loader.py                    — Carga dinamica de modelos generados por Fase 1
    knowledge/                         — TrackerMemoryWriter (sim observations → KG)
    recall/                            — retrieve_context tool sobre Knowledge Backbone
    nlsql.py                           — NL→SQL sobre experiments, models, memories, simulation_observations
    charts.py, critical_events.py      — Cards y visualizaciones para la UI
    api.py                             — FastAPI + WebSocket backend
    loop.py                            — Agent loop y dispatcher
    templates/                         — Plantilla LaTeX para informes
  backend/                             — Config de despliegue backend (Docker/Railway)
  frontend/                            — Frontend React + Vite + Tailwind
  tests/                               — Tests unitarios e integracion
  docs/specs/                          — Specs de diseno por fase

shared/                                — Storage compartido (Postgres, MinIO, Neo4j, Qdrant)
docker-compose.yml                     — Stack completo: postgres, minio, qdrant, neo4j, web
docs/                                  — Documentos de referencia (TFM Denis, knowledge-architecture)
```

---

## Punto de integracion

Las dos fases se conectan a traves de:

1. **Protocol `DecisionModel`** — interfaz con tres metodos (`decide()`, `update()`, `get_state()`). La Fase 1 implementa modelos concretos con tipos propios; la Fase 2 usa duck typing con percepciones como `dict`. Sin adaptador.
2. **Knowledge Backbone compartido** — Neo4j + Qdrant + Postgres. La Fase 1 escribe paradigmas, formulaciones, specs, modelos y memorias de pipeline; la Fase 2 lee contexto via `retrieve_context` y escribe observaciones de simulacion.
3. **Artefactos compartidos** — MinIO guarda reports, deep research, formulaciones, specs JSON, modelos generados, tests y trazas por `run_id`.

---

## Setup

Requiere Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ y Docker.

```bash
# 1. Servicios compartidos (Postgres, MinIO, Neo4j, Qdrant)
docker compose up -d

# 2. Fase 1
cd phase1-pablo && uv sync && cd ..

# 3. Fase 2 (backend)
cd phase2-juan
uv sync
cp .env.example .env   # configurar OPENROUTER_API_KEY (y opcionalmente VOYAGE_API_KEY)
cd ..

# 4. Fase 2 (frontend)
cd phase2-juan/frontend && npm install
```

## Uso

```bash
# CLI interactivo
cd phase2-juan && uv run simlab

# Web UI
cd phase2-juan && uv run uvicorn simlab.api:app --port 8000   # backend
cd phase2-juan/frontend && npm run dev                         # frontend → localhost:5173
```

Si el puerto 8000 esta ocupado, levanta el backend en otro puerto y pasalo al frontend via env:

```bash
uv run uvicorn simlab.api:app --port 8100
VITE_API_PORT=8100 npm run dev
```

## Tests

```bash
# Fase 2 — Python
cd phase2-juan && uv run pytest tests/ -v

# Fase 2 — Playwright (e2e + mock)
cd phase2-juan/frontend && npx playwright test
# Si tu backend no esta en 8000:
PLAYWRIGHT_BASE_URL=http://localhost:5175 npx playwright test

# Fase 1
cd phase1-pablo && uv run pytest tests/ -v
```

---

## Stack tecnico

| Componente | Tecnologia |
| --- | --- |
| Lenguaje | Python 3.12+ (uv) |
| LLM | Claude via OpenRouter (Anthropic SDK) |
| Backend | FastAPI + WebSocket |
| Frontend | React 19 + Vite + Tailwind CSS v4 |
| Tests | pytest + Playwright (e2e) |
| Persistencia relacional | Postgres 17 |
| Object store | MinIO (S3-compatible) |
| Knowledge graph | Neo4j 5 (HippoRAG PPR) |
| Vector + sparse search | Qdrant (dense + BM25 nativo) |
| Reranker / embeddings | Voyage AI (opcional, degrada graciosamente) |
| Informes | LaTeX (tectonic) → PDF |
| Orquestacion | Docker Compose |
