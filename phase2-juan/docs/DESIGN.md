# Fase 2: Diseno del Laboratorio Virtual de Simulacion

**TFG**: Laboratorio virtual para la simulacion y analisis de paradigmas de toma de decisiones humanas mediante agentes inteligentes

---

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

---

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

---

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

---

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

---

## 5. Integracion con Fase 1

Los `.py` generados por el Builder de Pablo se colocan en `phase1-pablo/examples/sample-run/builder/`. El `model_loader` de la Fase 2 los descubre automaticamente:

1. Escanea `builder/` buscando `*_model.py`
2. Importa cada modulo y busca clases con `decide/update/get_state`
3. El Orchestrator presenta los modelos al usuario
4. Al simular, se instancian con semilla para reproducibilidad

Multiples modelos pueden ejecutarse en el **mismo environment** para comparacion directa.

---

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

---

## 7. Experiment Store: persistencia y trazabilidad

### Motivacion

Los datos de simulacion no pueden vivir solo en memoria (`Orchestrator._state`). Necesitamos persistencia entre sesiones, historial, comparacion cross-experiment y reproducibilidad.

La solucion combina dos conceptos de data engineering:

1. **Pipeline de datos estructurado** — todos los artefactos del pipeline (spec, events, tracker output, analyst output, PDF) persisten en disco.
2. **Experiment tracking** — cada ejecucion del pipeline es un *experimento* con ID unico, metadatos de configuracion y estado de progreso.

### Schema (implementado)

La DB es SQLite en `data/labtfg.db` (gitignored). Paquete compartido `shared/` con `store.py`.

```
models
  ├── formulation_id  TEXT PRIMARY KEY   -- e.g. "homeostatic-regulation_drive_reduction_rl"
  ├── class_name      TEXT NOT NULL      -- e.g. "HomeostaticDriveReductionRL"
  ├── paradigm        TEXT               -- e.g. "homeostatic-regulation"
  ├── description     TEXT               -- docstring del modulo
  ├── file_path       TEXT NOT NULL      -- ruta al *_model.py
  ├── registered_at   TIMESTAMP
  └── metadata_json   TEXT               -- JSON libre para metadatos extra

experiments
  ├── id              TEXT PRIMARY KEY (UUID)
  ├── created_at      TIMESTAMP
  ├── updated_at      TIMESTAMP
  ├── description     TEXT               -- prompt original del usuario
  ├── status          TEXT               -- created | simulated | tracked | analyzed | reported
  ├── spec_json       TEXT               -- JSON spec del environment
  ├── models_used     TEXT               -- JSON array de formulation_ids
  ├── steps           INTEGER
  ├── seed            INTEGER | NULL
  ├── events_json     TEXT               -- eventos serializados (sin model_state)
  ├── replay_json     TEXT               -- frames para el replay del frontend
  ├── tracker_json    TEXT               -- salida completa del Tracker
  ├── analyst_json    TEXT               -- salida completa del Analyst
  └── pdf_path        TEXT               -- ruta al PDF generado
```

Diseno simplificado: JSON blobs dentro de `experiments` en vez de tablas normalizadas. Suficiente para el volumen esperado y evita joins innecesarios. Si en el futuro se necesitan queries SQL granulares (e.g. "media de reward del modelo X en los ultimos 10 experimentos"), se puede normalizar a tablas separadas (`experiment_agents`, `events`, `tracker_results`, etc.).

### Integracion con la arquitectura

El cambio es **no-invasivo** — el `Orchestrator._state` sigue funcionando igual, y la persistencia se anade como efecto secundario:

1. **`shared/store.py`** — inicializa DB, expone `create_experiment()`, `update_experiment()`, `get_experiment()`, `list_experiments()`, `register_model()`, `list_models()`, `get_model()`.
2. **`orchestrator.py`** — despues de cada paso del pipeline, llama a `update_experiment()` con el status y los datos correspondientes.
3. **`model_loader.py`** — al descubrir modelos de la Fase 1, los registra automaticamente en la tabla `models` (idempotente via INSERT OR REPLACE).
4. **`tools.py`** — ademas de los 3 tools de simulacion (current experiment), expone 2 tools de DB: `list_past_experiments` y `get_experiment_analysis` para consultas cross-experiment.
5. **Orchestrator tool `list_experiments`** — permite al usuario ver historial desde el chat.
6. **Analyst** — tiene acceso a los 5 tools (3 de simulacion + 2 de DB) para comparar el experimento actual con experimentos pasados.

### Capacidades

- **Historial**: "muestrame los ultimos 5 experimentos"
- **Comparacion cross-experiment**: el Analyst puede consultar resultados de experimentos pasados y comparar metricas, patrones y comportamientos
- **Reproducibilidad**: mismo spec + seed + modelo = mismos resultados
- **Persistencia entre sesiones**: cerrar y abrir el lab no pierde datos
- **Registro de modelos**: los modelos descubiertos de la Fase 1 se registran en la DB con paradigma, clase y ruta

### Tecnologia

**SQLite** (`sqlite3` stdlib, zero dependencias). Fichero en `data/labtfg.db` (root del repo, gitignored). WAL mode habilitado para lecturas concurrentes.

---

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
- Experiment Store: persistencia SQLite con historial, reproducibilidad y comparacion cross-experiment
- Registro automatico de modelos en DB al descubrirlos
- Analyst con tools de DB para comparacion cross-experiment
