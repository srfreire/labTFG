# Fase 2: Diseno del Laboratorio Virtual de Simulacion

**TFG**: Laboratorio virtual para la simulacion y analisis de paradigmas de toma de decisiones humanas mediante agentes inteligentes
## 1. Vision general

Este TFG es la segunda parte de un proyecto de dos fases:

- **Fase 1** (Pablo): pipeline de agentes LLM que investiga paradigmas de toma de decisiones, los formaliza y genera codigo Python (`DecisionModel`) listo para simular.
- **Fase 2** (este TFG): infraestructura para ejecutar esos modelos en un environment, observar su comportamiento, analizarlo y generar informes.

El sistema es una **arquitectura multi-agente** donde un usuario interactua con un **orquestador conversacional** que coordina cuatro agentes especializados:

```
Usuario (CLI / Web UI) → Orchestrator
    → Architect  (configura environment)
    → Tracker    (registra eventos y trayectorias)
    → Analyst    (identifica patrones)
    → Reporter   (genera informes PDF)
```

El usuario **solo habla con el Orchestrator**. Este interpreta la peticion y delega en los subagentes, coordinando el flujo: environment → simulacion → observacion → analisis → informe.
## 2. Decisiones de diseno

| Decision | Valor | Razon |
| --- | --- | --- |
| Tipo de mundo | Grid 2D | YAGNI — se amplia si hace falta |
| Agentes de simulacion | Codigo Python (reglas, EDOs, RL) | Nunca LLM en runtime de simulacion |
| Multi-agente | Si, desde el inicio | Comparacion de paradigmas requiere multiples agentes |
| Integracion Fase 1 | Duck typing directo | Los modelos de Pablo implementan `decide/update/get_state` — sin adapter |
| Acciones/recursos | Configuracion dinamica via JSON spec | El Architect genera specs, `spec_to_environment` los instancia |
| API LLM | `anthropic` SDK + loop manual de tool use | Compatible con OpenRouter, consistente con Fase 1 |
| Frontend | React + Vite + Tailwind + WebSocket | Dashboard en tiempo real con replay de simulaciones |
## 3. Los 5 agentes

### Orchestrator (Sonnet)
Punto de entrada conversacional. Interpreta peticiones del usuario, llama a los subagentes via tool use, presenta resultados y sugiere proximos pasos. Comportamiento proactivo: no ejecuta todo automaticamente, propone y deja que el usuario decida.

### Architect (Haiku)
Genera JSON specs de environment a partir de descripciones en lenguaje natural. Valida el spec con una tool y se autocorrige si falla. No instancia el environment (eso lo hace `spec_to_environment`).

### Tracker (Sonnet)
Observa los Events de una simulacion completada. Tiene tools para acceder a eventos, trayectorias y estado interno de los agentes. Produce un JSON estructurado con trayectorias, episodios y resumen.

### Analyst (Sonnet)
Procesa la salida del Tracker para identificar patrones de comportamiento, anomalias y comparaciones entre agentes. Produce JSON con patrones, comparaciones y metricas.

### Reporter (Haiku)
Genera informes PDF via LaTeX (compilado con tectonic). Lee investigacion de la Fase 1 para contextualizar. Produce documentos con portada USC, indice, tablas y conclusiones.
## 4. Environment

Framework en Python puro (sin LLMs) que define el mundo de simulacion.

### Conceptos clave

| Concepto | Que es |
| --- | --- |
| `Grid` | Espacio 2D (ancho x alto) |
| `Resource` | Objeto en el grid con propiedades |
| `Agent` | Posicion + DecisionModel + alive |
| `Action` | Lo que un agente hace en un step (name + params) |
| `ActionRule` | Conecta un nombre de accion con un Effect |
| `Effect` | `MoveEffect`, `ConsumeEffect`, `NoopEffect` |
| `Event` | Registro de algo que paso en un step |

### Flujo de un step

```
Para cada agente vivo:
  1. Percepcion → _build_perception(agent) → dict
  2. Decision  → decision_model.decide(perception) → Action
  3. Ejecucion → _apply_action(agent, action) → reward, result
  4. Update    → decision_model.update(action, reward, new_perception)
  5. Snapshot  → decision_model.get_state() → dict
  6. Registro  → Event con accion + outcome
```

### DecisionModel (interfaz compartida)

```python
def decide(self, perception: dict) -> Action
def update(self, action: Action, reward: float, new_perception: dict) -> None
def get_state(self) -> dict
```

Duck typing — los modelos de la Fase 1 implementan estos tres metodos directamente. Sin adapter, sin Protocol formal.
## 5. Integracion con Fase 1

Los `.py` generados por el Builder de Pablo se colocan en `phase1-pablo/examples/sample-run/builder/`. El `model_loader` de la Fase 2 los descubre automaticamente:

1. Escanea `builder/` buscando `*_model.py`
2. Importa cada modulo y busca clases con `decide/update/get_state`
3. El Orchestrator presenta los modelos al usuario
4. Al simular, se instancian con semilla para reproducibilidad

Multiples modelos pueden ejecutarse en el **mismo environment** para comparacion directa.
## 6. Stack tecnico

| Componente | Tecnologia |
| --- | --- |
| Lenguaje | Python 3.12+ (uv) |
| LLM | Claude via OpenRouter (Anthropic SDK) |
| Modelos | Haiku 4.5 (Architect, Reporter) + Sonnet 4.5 (Tracker, Analyst, Orchestrator) |
| Backend | FastAPI + WebSocket |
| Frontend | React + Vite + Tailwind CSS |
| Informes | LaTeX (tectonic) → PDF |
| Tests | pytest + Playwright (e2e) |

### Por que API directa y no Agent SDK

1. **Compatibilidad con OpenRouter** — el Agent SDK no funciona con proveedores alternativos
2. **Consistencia con Fase 1** — Pablo usa el mismo patron
3. **Simplicidad** — el loop de tool use son ~55 lineas (`runtime/loop.py`)
4. **Control total** — cada agente define sus tools, prompt y modelo sin abstracciones intermedias
## 7. Experiment Store: persistencia y trazabilidad

### Motivacion

Los datos de simulacion no pueden vivir solo en memoria (`Orchestrator._state`). Necesitamos persistencia entre sesiones, historial, comparacion cross-experiment y reproducibilidad.

La solucion combina dos conceptos de data engineering:

1. **Pipeline de datos estructurado** — todos los artefactos del pipeline (spec, events, tracker output, analyst output, PDF) persisten en disco.
2. **Experiment tracking** — cada ejecucion del pipeline es un *experimento* con ID unico, metadatos de configuracion y estado de progreso.

### Schema (implementado)

La persistencia es **Postgres** via SQLAlchemy async, definida en `shared/shared/models.py`. Las tablas relevantes son `models` y `experiments`. El stack se levanta con `docker compose up`; no hay fallback SQLite.

```
models                                    -- tabla shared.models.Model
  ├── id              UUID PRIMARY KEY
  ├── class_name      VARCHAR(255) NOT NULL  -- e.g. "DriveReductionRLModel"
  ├── paradigm        VARCHAR(255) NOT NULL  -- e.g. "homeostatic-regulation"
  ├── formulation     VARCHAR(255) NOT NULL  -- e.g. "drive-reduction-rl"
  ├── description     TEXT
  ├── run_id          UUID FK runs(id)       -- Phase 1 run que produjo el modelo
  ├── s3_model_key    VARCHAR(500) NOT NULL  -- key en MinIO con el .py
  ├── s3_test_key     VARCHAR(500)
  ├── registered_at   TIMESTAMP
  └── metadata        JSONB
  UNIQUE (run_id, paradigm, formulation)

experiments                               -- tabla shared.models.Experiment
  ├── id              UUID PRIMARY KEY
  ├── created_at      TIMESTAMP
  ├── updated_at      TIMESTAMP
  ├── description     TEXT NOT NULL
  ├── status          VARCHAR(50)         -- created | simulated | tracked | analyzed | reported
  ├── spec            JSONB
  ├── models_used     JSONB
  ├── steps           INTEGER
  ├── seed            INTEGER
  ├── s3_events_key   VARCHAR(500)        -- eventos serializados en MinIO
  ├── s3_replay_key   VARCHAR(500)        -- frames del replay en MinIO
  ├── s3_tracker_key  VARCHAR(500)
  ├── s3_analyst_key  VARCHAR(500)
  ├── s3_pdf_key      VARCHAR(500)
  ├── s3_tex_key      VARCHAR(500)
  └── s3_charts_prefix VARCHAR(500)
```

Las salidas grandes (events, tracker, analyst, PDF, replay) viven como objetos en MinIO y la fila guarda solo el `s3_*_key`. Esto mantiene las filas compactas y permite consultas rapidas sin deserializar JSON pesado.

### Integracion con la arquitectura

La persistencia se integra como efecto secundario del pipeline:

1. **`shared/shared/models.py`** — define los ORM `Model`, `Experiment`, `Run`, `Artifact`, `Memory`. Acceso async via `shared.db.get_session()`.
2. **`orchestrator.py`** — despues de cada paso del pipeline, hace `update` async sobre la fila de `Experiment` con el status y los `s3_*_key` correspondientes.
3. **`model_loader.py`** — `discover_models()` consulta `select(Model)` desde Postgres y `load_model()` baja el `.py` desde MinIO via `s3_model_key`. El registro de modelos lo hace Phase 1 (no Phase 2).
4. **`tools.py`** — ademas de los tools de simulacion, expone tools de consulta cross-experiment (`list_past_experiments`, `get_experiment_analysis`) que leen de Postgres.
5. **Orchestrator tool `list_experiments`** — permite al usuario ver historial desde el chat.
6. **Analyst** — usa los tools cross-experiment para comparar el experimento actual con pasados.

### Capacidades

- **Historial**: "muestrame los ultimos 5 experimentos"
- **Comparacion cross-experiment**: el Analyst puede consultar resultados de experimentos pasados y comparar metricas, patrones y comportamientos
- **Reproducibilidad**: mismo spec + seed + modelo = mismos resultados
- **Persistencia entre sesiones**: cerrar y abrir el lab no pierde datos
- **Registro de modelos**: los modelos descubiertos de la Fase 1 se registran en la DB con paradigma, clase y ruta

### Tecnologia

**Postgres** via SQLAlchemy 2.0 async (`asyncpg` driver). Migraciones con Alembic en `shared/migrations/`. Levantar con `docker compose up`. No hay fallback local — Phase 2 requiere los servicios compartidos.
## 8. Estado de implementacion

### Completado

- Environment base generico (effect types, ActionRule, ResourceRule)
- Spec validation + conversion (`spec.py`)
- Runtime agentico compartido (`loop.py`)
- Los 5 agentes (Architect, Tracker, Analyst, Reporter, Orchestrator)
- CLI interactivo (`uv run simlab`)
- Web UI: dashboard dark, chat WebSocket, replay animado, data cards, panel de agentes
- Dynamic model loader para modelos de la Fase 1
- Comparacion multi-modelo en mismo environment
- Pipeline completo e2e testeado con Playwright
- Experiment Store: persistencia Postgres con historial, reproducibilidad y comparacion cross-experiment
- Registro automatico de modelos en Postgres al descubrirlos (lo hace Phase 1)
- Analyst con tools de Postgres para comparacion cross-experiment
