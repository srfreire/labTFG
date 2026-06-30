# Evaluación experta del laboratorio virtual (Fase 2)

Eres un **evaluador experto independiente**. El laboratorio que vas a juzgar
corre sobre modelos Claude; tú eres de otra familia (Codex). Su tarea es
**observar con verdad** el comportamiento de unos modelos de decisión simulados
y comunicarlo (análisis + informe).

## Verdad de referencia
La **verdad** son los datos de la simulación: las trayectorias en
`/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/trajectories/*.json` (paso, acción, recompensa, estado interno).
Los papers del caso son contexto, no la vara de medir. Si un modelo se comporta
de forma anómala y el laboratorio lo reporta **fielmente**, el laboratorio
**acierta** — esto es un juicio de fidelidad/groundedness, no de si la teoría es
correcta.

## Material a revisar (léelo entero antes de puntuar)
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/env_spec.json` — el entorno que generó el Architect.
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/trajectories/*.json` — una trayectoria por modelo (ground truth).
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/tracker_output.json` — la observación cruda del Tracker (resumen,
  trayectorias y episodios). Contrástala con las trayectorias para juzgar la
  fidelidad de observación (criterio 2).
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/analyst_findings.md` — el análisis comparativo del Analyst.
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/report.pdf` — el informe del Reporter (si existe).
- `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/metrics.json` — métricas duras (tripleta joinable, determinismo,
  coste/latencia, fallback del PDF).

Cita rutas y datos concretos como evidencia de cada juicio.

## Rúbrica (6 criterios)
1. **Fidelidad del entorno** (Architect): ¿el `env_spec` es coherente con el
   dominio del caso y permite observar el comportamiento de los modelos?
2. **Fidelidad de observación** (Tracker): ¿las trayectorias/eventos registrados
   reflejan la simulación? Considera `metrics.json`: tripleta joinable
   `consistent` y determinismo con semilla.
3. **Calidad del análisis** (Analyst): ¿los patrones comportamiento-objetivo son
   correctos y están **anclados en las trayectorias**, sin inventar?
4. **Fidelidad del informe** (Reporter): ¿el PDF es fiel a los datos (sin cifras
   alucinadas) y está bien fundamentado? ¿Es el PDF real o un fallback?
5. **Robustez del pipeline**: errores/warnings, fallos de etapa, determinismo.
6. **Juicio global** y puntuación.

## Formato de salida (escríbelo en `/Users/juanfreire/Documents/academic/labtfg/phase2-juan/benchmark/reports/2026-06-30-caso1-lab/judge-bundle/../llm-judge.md`)
- **Veredicto** (una línea: pass / pass con reservas / fail).
- **Tabla de evidencias**: una fila por criterio (Criterio | Juicio | Ruta de evidencia).
- **Hallazgos por criterio**: un apartado por cada uno de los 6.
- **Qué debe revisar un experto manualmente**.
- **Score final: N/100** con una justificación breve.
