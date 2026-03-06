# Fase 2: Diseño del Laboratorio Virtual de Simulación

**TFG**: Laboratorio virtual para la simulación y análisis de paradigmas de toma de decisiones humanas mediante agentes inteligentes

**Alumno**: Juan Freire Alvarez
**Tutor**: Eduardo Manuel Sánchez Vila

---

## 1. Contexto

Este TFG es la segunda parte de un proyecto de dos fases:

- **Fase 1** (complementaria): modelado de agentes autónomos basados en paradigmas de toma de decisiones humanas. Revisión de literatura, síntesis de paradigmas, formalización matemática y traducción a agentes.
- **Fase 2** (este TFG): infraestructura para simular, observar, analizar y documentar el comportamiento de esos agentes.

Como punto de partida disponemos de un script Python de referencia (`survival_metabolicModel_behave_clean_Denis.py`) que implementa un modelo metabólico de supervivencia con reglas if/else. Este script sirve como caso de uso inicial pero no como base de código — el diseño será genérico.

---

## 2. Visión general

El sistema se construye como una **arquitectura multi-agente** donde un usuario interactúa con un **orquestador conversacional** que coordina cuatro agentes especializados:

```
Usuario (CLI / Web UI)
    │
    ▼
┌─────────────────────────────────┐
│         ORQUESTADOR             │
│   (interfaz conversacional)     │
│                                 │
│   "Crea un environment con 10  │
│    organismos, recursos         │
│    limitados, y observa cómo   │
│    evoluciona la estrategia    │
│    de alimentación"            │
└─────────┬───────────────────────┘
          │
          ├──► Agente Plataforma ──► configura/construye el environment
          ├──► Agente Observador ──► monitoriza la simulación
          ├──► Agente Analítico ──► analiza datos recogidos
          └──► Agente Redactor  ──► genera informes
```

El usuario **solo habla con el orquestador**. Este interpreta la petición y delega en los agentes apropiados, coordinando el flujo completo: construcción del environment → ejecución → observación → análisis → informe.

---

## 3. Agentes del sistema

### 3.1 Orquestador

- **Rol**: punto de entrada del usuario. Interpreta peticiones en lenguaje natural y coordina a los demás agentes.
- **Responsabilidades**:
  - Parsear la intención del usuario (qué quiere simular, qué observar, qué analizar)
  - Decidir qué agentes invocar y en qué orden
  - Gestionar el flujo de datos entre agentes
  - Devolver resultados al usuario de forma coherente

### 3.2 Agente Plataforma de Simulación

- **Rol**: construir y configurar environments de simulación sobre una base genérica definida en Python.
- **Responsabilidades**:
  - Recibir especificaciones del orquestador (objetivos, recursos, restricciones, número de agentes)
  - Instanciar y parametrizar un environment concreto a partir del framework base
  - Ejecutar la simulación paso a paso
- **Input**: especificación del environment (parámetros, reglas, condiciones)
- **Output**: environment configurado y listo para ejecutar, datos de simulación

### 3.3 Agente Observador

- **Rol**: monitorizar el comportamiento de los agentes durante la simulación.
- **Responsabilidades**:
  - Registrar eventos relevantes en cada paso de la simulación
  - Capturar episodios (secuencias de eventos significativas)
  - Trazar trayectorias de decisión de cada agente
- **Input**: datos en tiempo real de la simulación
- **Output**: log estructurado de eventos, episodios y trayectorias

### 3.4 Agente Analítico

- **Rol**: procesar los datos del Observador para extraer patrones.
- **Responsabilidades**:
  - Identificar correlaciones entre comportamientos y consecución de objetivos
  - Detectar estrategias emergentes
  - Comparar rendimiento entre agentes o entre configuraciones
- **Input**: logs del Observador
- **Output**: patrones identificados, métricas, comparativas

### 3.5 Agente Redactor

- **Rol**: generar informes estructurados con los resultados.
- **Responsabilidades**:
  - Sintetizar conclusiones del análisis
  - Proponer mejoras en los modelos de comportamiento
  - Generar documentación legible (Markdown, PDF)
- **Input**: resultados del Agente Analítico
- **Output**: informe final estructurado

---

## 4. Environment base (Python)

Se diseñará un **framework genérico en Python** que define las abstracciones fundamentales de cualquier simulación. Los agentes inteligentes (Claude) no generan código desde cero — parametrizan y extienden estas abstracciones.

### Conceptos clave del framework

| Concepto | Descripción |
|----------|-------------|
| `Environment` | Mundo de la simulación. Contiene recursos, agentes y reglas. |
| `Agent` | Entidad que toma decisiones dentro del environment. |
| `Resource` | Elemento del environment que los agentes pueden consumir/usar. |
| `Action` | Acción que un agente puede realizar en un paso. |
| `Step` | Unidad de tiempo de la simulación. |
| `Event` | Registro de algo que ocurrió en un step. |
| `Objective` | Criterio de éxito/fracaso de la simulación. |

### Ejemplo conceptual

```python
class Environment:
    """Mundo de la simulación."""
    agents: list[Agent]
    resources: list[Resource]
    objectives: list[Objective]
    constraints: dict
    step_count: int

    def step(self) -> list[Event]:
        """Avanza un paso de simulación."""
        ...

    def is_finished(self) -> bool:
        """Comprueba si se cumplieron los objetivos o se agotó el tiempo."""
        ...

class Agent:
    """Entidad que toma decisiones."""
    state: dict
    decision_model: str  # paradigma de toma de decisiones

    def decide(self, perception: dict) -> Action:
        """Decide qué acción tomar dado lo que percibe."""
        ...

class Event:
    """Registro de un acontecimiento."""
    step: int
    agent_id: str
    action: Action
    outcome: dict
```

El Agente Plataforma recibe instrucciones del orquestador y configura instancias concretas de estas clases (por ejemplo: un environment de supervivencia con 10 organismos, comida limitada, y agentes con modelo homeostático).

---

## 5. Stack tecnológico

| Componente | Tecnología | Justificación |
|------------|------------|---------------|
| Lenguaje | Python | Continuidad con el script de referencia; ecosistema científico |
| LLM | Claude (Anthropic) | Capacidades de razonamiento y tool_use nativas |
| SDK | Anthropic Python SDK | Integración directa sin frameworks intermedios |
| Orquestación | Claude tool_use | Cada agente = conjunto de tools que el orquestador invoca |
| Interfaz CLI | Python (argparse/rich) | MVP rápido, interacción directa |
| Interfaz Web | Por definir (fase posterior) | Se añadirá sobre la lógica ya construida |
| Datos | JSON / SQLite | Logs de simulación, resultados de análisis |

### Decisión: sin frameworks de agentes

Se opta por **no usar frameworks** como LangGraph, CrewAI o AutoGen. Razones:

1. **Control total** sobre el flujo de comunicación entre agentes
2. **Menos dependencias** — el sistema depende solo del SDK de Anthropic
3. **Transparencia** — todo el código de orquestación es explícito y auditable
4. **Adecuación académica** — en un TFG es preferible demostrar comprensión del mecanismo a usar abstracciones de terceros

La orquestación se implementa con el mecanismo de **tool_use** de Claude: cada agente especializado expone sus capacidades como tools, y el orquestador (un agente Claude) decide cuáles invocar según la petición del usuario.

---

## 6. Flujo de uso típico

```
1. Usuario → Orquestador:
   "Simula 100 pasos con 5 organismos en un entorno con comida
    escasa. Quiero ver cómo cambian las estrategias de búsqueda."

2. Orquestador → Agente Plataforma:
   Configura environment (5 agentes, recursos escasos, 100 steps)

3. Agente Plataforma ejecuta la simulación
   → genera datos paso a paso

4. Orquestador → Agente Observador:
   Procesa los datos, registra eventos y trayectorias

5. Orquestador → Agente Analítico:
   Analiza los logs del observador, identifica patrones

6. Orquestador → Agente Redactor:
   Genera informe con conclusiones y propuestas

7. Orquestador → Usuario:
   Presenta el informe + visualizaciones relevantes
```

---

## 7. Desarrollo incremental

### Fase 2.1 — MVP (CLI)
- Environment base en Python (clases abstractas)
- Primer caso de uso concreto: modelo metabólico basado en el script de Denis
- Orquestador básico via CLI
- Agente Plataforma funcional
- Agente Observador básico (logging de eventos)

### Fase 2.2 — Análisis e informes
- Agente Analítico funcional
- Agente Redactor funcional
- Pipeline completo: simulación → observación → análisis → informe

### Fase 2.3 — Web UI
- Interfaz web sobre la lógica existente
- Visualización de simulaciones en tiempo real
- Gráficas interactivas del análisis

---

## 8. Justificación de decisiones de diseño

### El environment base como código Python puro es la pieza central

La clave de la arquitectura es que el LLM (Claude) **no genera código desde cero**. El environment base define una API clara: qué es un recurso, qué es un agente, qué es un paso de simulación, qué es una acción. El Agente Plataforma solo tiene que **parametrizar y extender** esas abstracciones. Esto reduce drásticamente los errores del LLM y hace que los resultados sean predecibles y verificables.

En la práctica, la petición del usuario se traduce en configuración (número de agentes, tipo de recursos, reglas de interacción), no en código arbitrario.

### Claude SDK con tool_use es suficiente para la orquestación

No se necesita un framework de agentes. El mecanismo de `tool_use` de Claude permite definir cada capacidad de cada agente como una herramienta (tool). El orquestador es simplemente una instancia de Claude que tiene acceso a todas las tools y decide cuáles invocar según la petición del usuario.

Esto es más transparente que un framework, más fácil de depurar, y en un contexto académico permite demostrar que se entiende el mecanismo subyacente en vez de depender de abstracciones de terceros.

### CLI primero, Web después

Separar la lógica de negocio de la interfaz es fundamental. Construir el CLI primero obliga a que toda la lógica de orquestación, simulación, observación y análisis funcione de forma independiente. La Web UI se construye después como una capa de presentación sobre la misma lógica, sin duplicar código.

### Gestión del riesgo: límites del Agente Plataforma

El principal riesgo de diseño es definir **cuánta libertad tiene el Agente Plataforma** para modificar el environment:

- **Solo parámetros** (número de agentes, cantidad de recursos, duración): seguro pero poco flexible.
- **Generar código arbitrario** (nuevas clases, nuevas reglas): muy flexible pero difícil de controlar y validar.
- **Punto medio recomendado**: el Agente Plataforma puede seleccionar y combinar componentes predefinidos (tipos de agentes, tipos de recursos, reglas de interacción) y configurar sus parámetros. Si necesita algo que no existe, lo propone al usuario en vez de generarlo directamente.

---

## 9. Riesgos y decisiones abiertas

| Riesgo / Decisión | Descripción | Estado |
|-------------------|-------------|--------|
| Límites del Agente Plataforma | ¿Cuánta libertad tiene para modificar el environment? Solo parámetros vs. generar código | Por definir |
| Coste de API | Cada interacción con el orquestador implica llamadas a Claude | Monitorizar |
| Determinismo | Las simulaciones deben ser reproducibles (seeds) | Por implementar |
| Extensibilidad | ¿Cómo se añaden nuevos paradigmas de decisión al framework? | Por diseñar |
| Formato de datos | Estructura exacta de los logs del Observador | Por definir |
