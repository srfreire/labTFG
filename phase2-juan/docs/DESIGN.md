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

Actualmente todos los datos de simulacion viven en memoria (`Orchestrator._state`). Cuando la sesion termina, se pierde todo. No hay forma de comparar un experimento de hoy con uno de ayer, ni de reproducir resultados, ni de hacer analisis cross-experiment.

La solucion combina dos conceptos de data engineering:

1. **Pipeline de datos estructurado** — schema relacional para todos los artefactos del pipeline (events, tracker output, analyst output), con persistencia en disco.
2. **Experiment tracking** — cada ejecucion del pipeline es un *experimento* con ID unico, metadatos de configuracion y estado de progreso. Permite historial, comparacion y reproducibilidad.

### Schema

```
experiments
  ├── id            TEXT PRIMARY KEY (UUID)
  ├── created_at    TIMESTAMP
  ├── description   TEXT              -- prompt original del usuario
  ├── spec_json     TEXT              -- JSON spec del environment
  ├── status        TEXT              -- created | simulated | tracked | analyzed | reported
  ├── steps         INTEGER
  └── seed          INTEGER | NULL    -- para reproducibilidad

experiment_agents
  ├── experiment_id TEXT  FK → experiments
  ├── agent_id      TEXT              -- e.g. "agent_0"
  ├── model_name    TEXT              -- e.g. "drive_reduction"
  ├── model_class   TEXT              -- e.g. "DriveReductionModel"
  └── initial_x, initial_y  INTEGER

events
  ├── experiment_id  TEXT  FK → experiments
  ├── step           INTEGER
  ├── agent_id       TEXT
  ├── action_name    TEXT
  ├── action_params  TEXT  (JSON)
  ├── reward         REAL
  ├── action_result  TEXT  (JSON)
  └── model_state    TEXT  (JSON)

tracker_results
  ├── experiment_id  TEXT  FK → experiments
  ├── summary        TEXT
  ├── trajectories   TEXT  (JSON)
  └── episodes       TEXT  (JSON)

analyst_results
  ├── experiment_id  TEXT  FK → experiments
  ├── patterns       TEXT  (JSON)
  ├── comparisons    TEXT  (JSON)
  └── metrics        TEXT  (JSON)

reports
  ├── experiment_id  TEXT  FK → experiments
  ├── pdf_path       TEXT
  └── generated_at   TIMESTAMP
```

### Integracion con la arquitectura existente

El cambio es **no-invasivo** — el `Orchestrator._state` sigue funcionando igual, y la persistencia se anade como efecto secundario:

1. **Nuevo modulo `store.py`** — inicializa DB, expone funciones `save_experiment()`, `save_events()`, `save_tracker_output()`, `load_experiment()`, `list_experiments()`, etc.
2. **`orchestrator.py`** — despues de cada paso del pipeline, llama a `store.save_*()`. El dict `_state` sigue intacto (backward compatible).
3. **`tools.py`** — las funciones de query pueden opcionalmente leer de DB dado un `experiment_id`, habilitando consultas cross-experiment.
4. **Nuevo tool `list_experiments()`** — el Orchestrator puede ofrecer historial y comparacion al usuario.

### Capacidades nuevas

- **Historial**: "muestrame los ultimos 5 experimentos"
- **Comparacion cross-experiment**: "compara drive_reduction de hoy vs ayer"
- **Reproducibilidad**: mismo spec + seed + modelo = mismos resultados
- **Analisis agregado**: metricas promediadas sobre N ejecuciones del mismo paradigma
- **Persistencia entre sesiones**: cerrar y abrir el lab no pierde datos

### Tecnologia

**SQLite** (`sqlite3` stdlib, zero dependencias). Fichero en `phase2-juan/data/experiments.db` (gitignored). Alternativa: DuckDB si se quiere enfatizar el angulo analitico (columnar, mejor para agregaciones), pero SQLite es suficiente para el volumen esperado.

---

## 8. Estado de implementacion

### Completado

- Environment base generico (effect types, ActionRule, ResourceRule)
- Spec validation + conversion (`spec.py`)
- Runtime agentico compartido (`runtime/loop.py`, `runtime/dispatcher.py`)
- Los 5 agentes (Architect, Tracker, Analyst, Reporter, Orchestrator)
- CLI interactivo (`uv run simlab`)
- Web UI: dashboard dark, chat WebSocket, replay animado, data cards, panel de agentes
- Dynamic model loader para modelos de la Fase 1
- Comparacion multi-modelo en mismo environment
- Pipeline completo e2e testeado con Playwright
