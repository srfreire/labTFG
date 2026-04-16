# sim-recall — General Specification

> Status: draft | Created: 2026-04-16 | Last updated: 2026-04-16

## Overview

Hace que Phase 2 sea consciente de su propia historia y del Knowledge Backbone. Introduce tres capacidades complementarias:

1. **Context retrieval (KG reads)** — Architect/Analyst/Reporter consultan el Knowledge Backbone vía la tool `retrieve_knowledge` de Pazos para enriquecer sus razonamientos con conocimiento científico estructurado (postulates, papers, variables, patrones previos) en vez de depender exclusivamente de lecturas textuales de MinIO.
2. **NL→SQL history query** — el usuario (y potencialmente los propios agentes) puede preguntar en lenguaje natural sobre sus ejecuciones pasadas ("¿qué paradigmas he probado con grid 10×10?", "¿cuándo falló por inanición el modelo drive-reduction?"). Una tool nueva genera SQL read-only sobre `experiments` + `models` + `memories` y devuelve filas formateadas.
3. **Chat history persistence** — las conversaciones con el Orchestrator, que hoy viven sólo en memoria del proceso, se persisten en una tabla nueva `chat_messages`. Esto da sustrato para que NL→SQL responda preguntas tipo *"¿qué te dije la semana pasada sobre addiction?"*.

Simétrico a sim-memory: sim-memory **escribe** observaciones al Knowledge Backbone; sim-recall **lee** del Knowledge Backbone y de la base de datos estructurada, además de garantizar que la conversación misma sea un dato consultable.

## Core Features

### Feature 1 — Context retrieval in Phase 2 agents

- **`retrieve_context` tool** en el Orchestrator (wrapper fino sobre `decisionlab.knowledge.retrieval.tool.retrieve_knowledge`).
- **Architect** la usa antes de generar specs para inspirar environments coherentes con paradigmas similares previos (TODO#3 del `CLAUDE.md`).
- **Analyst** la usa para contrastar patrones observados contra `Postulate` nodes del KG ("¿predice este paradigma que el modelo X se comporte así?").
- **Reporter** la usa para enriquecer el PDF con papers/autores/DOIs reales del grafo en vez de referencias genéricas.
- **Feature 1 absorbe** los TODO#2 (Analyst/Reporter del KG) y TODO#3 (Architect specs) del `CLAUDE.md`.
- **`read_predictions` NO se toca** en este scope — funciona y es una consulta puntual; si más adelante queremos sustituirlo, issue aparte.
- Graceful degradation: si Neo4j/Qdrant/Voyage caídos, `retrieve_context` devuelve lista vacía y el agente prosigue con su comportamiento actual.

### Feature 2 — NL→SQL history query

- **`query_history(question: str)` tool** disponible al Orchestrator (y exposed al chat).
- Genera SQL read-only sobre un **schema whitelist** (`experiments`, `models`, `memories`) usando Claude Haiku como traductor barato.
- Safeguards:
  - Read-only forzado (`SELECT` solamente; rechaza `INSERT`/`UPDATE`/`DELETE`/`DROP`/`CREATE`/`ALTER`).
  - `LIMIT` obligatorio (default 50, máx 500).
  - Timeout 5s.
  - Validación AST del SQL generado antes de ejecutar (parse con `sqlparse` y rechazo si no es `SELECT` o referencia tablas fuera del whitelist).
- Devuelve filas formateadas como markdown para inyectar en la respuesta del Orchestrator.
- Si la pregunta no es mapeable a SQL (fuera del dominio), el LLM devuelve `{"error": "out of scope"}` y la tool responde con mensaje amable al usuario.

### Feature 3 — Chat history persistence

- Nueva tabla `chat_messages` (Postgres) con:
  - `id UUID PK`, `session_id UUID` (agrupa mensajes de una misma sesión CLI/web), `experiment_id UUID FK nullable`, `role` (user/assistant/tool_result), `content TEXT`, `tool_name VARCHAR(50) NULL`, `created_at`.
- Hook en `Orchestrator.chat()`: tras cada turno, persiste `user` + `assistant` messages (y tool_result blocks).
- `session_id` se genera al arranque del Orchestrator; si la sesión pertenece a un experimento concreto, se liga.
- Consumible por Feature 2 (NL→SQL puede consultar esta tabla para preguntas tipo *"¿qué te pregunté sobre X?"*).
- Opcional (out-of-scope fase 1): embed en Qdrant colección `chat_messages_dense` para búsqueda semántica. Anotado como futuro.

## Out of Scope

- **Nuevos nodos Neo4j** (Simulation/Observation con aristas a Model) — se queda como TODO futuro, no se aborda aquí.
- **Migración a BM25 nativo de Qdrant** — depende de que aterrice P6-002 de Pazos; se aborda cuando suceda.
- **Sustituir `read_predictions`** por retrieve_knowledge — funciona como está; iteración futura si la fidelidad se vuelve insuficiente.
- **Frontend changes** — el web UI ya muestra experimentos; si el NL→SQL necesita UI dedicada es un proyecto separado.
- **Write access desde NL→SQL** — el scope es solo lectura. Modificaciones de datos siempre pasan por tools específicas con schema forzado.
- **Embed chat messages en Qdrant** (semantic search sobre el chat) — feature avanzada; suficiente con SQL en la v1.
- **Retention / pruning de chat_messages** — no gestionamos expiración; si la tabla crece sin límite, issue aparte.
- **Multi-usuario / auth** — una sola instancia, un solo usuario. Sin `user_id` en chat_messages por ahora.

## Data Model

### Tabla nueva: `chat_messages`

```sql
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  experiment_id UUID NULL REFERENCES experiments(id) ON DELETE SET NULL,
  role VARCHAR(20) NOT NULL,          -- 'user' | 'assistant' | 'tool_result'
  content TEXT NOT NULL,              -- texto plano o JSON serializado del bloque
  tool_name VARCHAR(50) NULL,         -- para tool_use/tool_result
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_chat_messages_session ON chat_messages(session_id);
CREATE INDEX ix_chat_messages_experiment ON chat_messages(experiment_id);
CREATE INDEX ix_chat_messages_created ON chat_messages(created_at);
```

### Tablas existentes consultadas (sin cambios)

- `experiments` — spec JSONB, models_used JSONB, steps, seed, status, s3_*_key pointers.
- `models` — paradigm, formulation, class_name, run_id.
- `memories` — content, namespace, metadata JSONB (ya creada por sim-memory).

Ningún cambio en estas tablas.

## Integrations

- **Postgres** — lectura (experiments/models/memories) y escritura (chat_messages).
- **Neo4j + Qdrant + Voyage** — consumidos a través de `decisionlab.knowledge.retrieval.tool.retrieve_knowledge`. No escribimos al KG.
- **Anthropic (Haiku)** — traducción NL→SQL (~$0.001 por query).
- **Alembic** — migración de la tabla `chat_messages`.

## User Flows

### Flow 1 — Architect consulta specs previas (Feature 1)

1. Usuario: "créame un entorno de recompensa con agentes homeostáticos".
2. Orchestrator llama `create_environment`.
3. El Architect, antes de generar el spec, llama `retrieve_context(query="homeostatic reward environments", namespace="paradigm")`.
4. Recibe facts como "Berridge separates wanting from liking (Paper: Dissecting components of reward, 2009)" y "Keramati's drive-reduction model requires parameters {learning_rate=0.1, ...}".
5. Genera un spec coherente con la literatura.

### Flow 2 — Reporter enriquece PDF con referencias reales (Feature 1)

1. Tras `generate_report`, el Reporter llama `retrieve_context(query=f"papers and authors for paradigm {paradigm}", namespace="paradigm", top_k=10)`.
2. Recibe lista de `Paper` nodes con title/year/doi/citation_count.
3. Genera la sección "References" del PDF con citas reales en vez de genéricas.

### Flow 3 — Usuario consulta historial (Feature 2)

1. Usuario: "¿qué paradigmas he probado con grid 10×10?".
2. Orchestrator llama `query_history(question=...)`.
3. Tool: Haiku genera `SELECT DISTINCT m.paradigm FROM experiments e JOIN ... WHERE e.spec->>'grid_width' = '10' AND e.spec->>'grid_height' = '10'`.
4. Validación: SELECT-only, LIMIT añadido, whitelist tables. OK.
5. Ejecuta, formatea como markdown table, devuelve al chat.

### Flow 4 — Usuario pregunta sobre conversación pasada (Feature 2 + 3)

1. Usuario: "¿qué te pregunté sobre drive reduction la semana pasada?".
2. `query_history` → Haiku genera `SELECT content, created_at FROM chat_messages WHERE content ILIKE '%drive reduction%' AND role='user' AND created_at > NOW() - INTERVAL '14 days'`.
3. Filas devueltas al chat con timestamps.

### Flow 5 — Analyst contrasta con postulates (Feature 1)

1. Tras `analyze_results`, el Analyst llama `retrieve_context(query=f"postulates for paradigm {paradigm}", namespace="paradigm")`.
2. Para cada `Postulate` node retornado, verifica contra los patrones observados en la simulación.
3. Añade a su análisis: "Observación consistente con Postulate P3 (dopamine mediates wanting, not liking)".

## Constraints & Non-Functional Requirements

- **Latencia**:
  - `retrieve_context`: mismo SLA que `retrieve_knowledge` de Pazos (~2s incluyendo CRAG). Llamadas por turno de agente, no hot-path.
  - `query_history`: Haiku NL→SQL ~800ms + SQL ~50ms + formateo = <1.5s P95.
  - Chat persistence: async background task o síncrono <10ms (Postgres insert simple).
- **Fiabilidad**: fallo en cualquiera de las 3 features **nunca** aborta el flow del Orchestrator. Logueo + degradación silenciosa.
- **Seguridad NL→SQL**:
  - AST whitelist (solo SELECT, solo 3 tablas).
  - Rechazo explícito de stored procedures, set-returning functions peligrosas, subqueries a tablas no-whitelisted.
  - Parámetros quoteados/escapados por SQLAlchemy text clause (no string concat).
  - Timeout de statement 5s en Postgres.
- **Coste**: Haiku NL→SQL ~$0.001/query. Retrieve_knowledge ya tiene su propio coste (~$0.001 CRAG). Ignorable.
- **Backward compat**: si ninguna feature activa (flags OFF), Phase 2 se comporta idénticamente al estado actual.

## Key Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Reuso vs reimplementación retrieval | Reutilizar `retrieve_knowledge` de Pazos vía wrapper | Zero duplicación; aprovecha su CRAG + RRF + reranker. |
| NL→SQL LLM | Haiku (no Sonnet) | Task simple, coste bajo, latencia baja. |
| Scope NL→SQL tables | `experiments` + `models` + `memories` + `chat_messages` | Cubre 95% de preguntas "qué hice / qué pasó". Si se necesitan más → issue aparte. |
| Validación SQL | AST parse con `sqlparse` + whitelist | Defensa en profundidad. LLM + regex no son suficientes. |
| Chat history granularity | 1 fila por mensaje (no por turno) | Consulta flexible. Tool_use y tool_result como filas separadas. |
| Ubicación tool handlers | `phase2-juan/simlab/recall/` (paquete nuevo) | Paralelo a `simlab/knowledge/` (writer) — simetría write/read. |
| `experiment_id` en chat_messages | Nullable FK | Conversaciones pueden no estar asociadas a un experiment (pregunta casual, setup). |
| Session ID generation | UUID al arrancar el Orchestrator | Agrupa mensajes de una misma "sesión CLI". Persiste entre reinicios si la sesión continúa (implementación: ver phase spec). |
| Feature flags | Reuse `ENABLE_KNOWLEDGE_WRITE` no aplica aquí — añadir `ENABLE_KNOWLEDGE_READ` y `ENABLE_CHAT_PERSISTENCE` | Flags separadas permiten activación incremental. |
| Chat message content format | Texto plano; tool_use/tool_result como JSON string | Simple, queryable. Si se complica, migrar a JSONB en futuro. |
