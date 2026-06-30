# Diseño — Migración de la evaluación de Pazos a la Fase 2

**Fecha:** 2026-06-30
**Autor:** Juan Freire Alvarez (Fase 2)
**Estado:** aprobado en brainstorming, pendiente de plan de implementación

## Contexto y objetivo

Pablo Pazos (Fase 1) commiteó una evaluación de su pipeline sobre dos casos de
corpus cerrado (`phase1-pablo/evals/`). Su evaluación tiene **dos piezas**:

1. **Run del pipeline con corpus cerrado** (`decisionlab eval run caso{1,2}`):
   restringe los tools de búsqueda del agente a los PDFs aportados, corre el
   pipeline entero y vuelca métricas duras en
   `evals/reports/<fecha>-<suite>/report.{json,md}` + un `artifact-bundle/`
   (estado de PG/MinIO/Neo4j + corpus). Para estos dos casos el YAML **no
   declara assertions**, así que el "PASS" es trivial: es **instrumentación**,
   no juicio de corrección.
2. **LLM-as-judge agéntico** (post-hoc): un agente (Codex/otra familia) lee el
   bundle y escribe `evals/judge-reports/<fecha>-<suite>-llm-judge.md` con
   veredicto, tabla de evidencias, hallazgos por criterio, sección "qué debe
   revisar un experto" y **score/100**. CASO1 = 72/100, CASO2 = 78/100, ambos
   "pass with reservations". El modelo juez no está nombrado en el texto
   commiteado de Pablo; Juan usará **Codex (GPT-5.x)** explícitamente.

**Objetivo:** construir una evaluación **paralela y similar** para la Fase 2 (el
laboratorio virtual), que se narrará en la memoria. Mismo método (run
instrumentada + juez agéntico con rúbrica y score/100), distinto **sujeto**: en
vez de juzgar el pipeline generador de Fase 1, se juzga el **laboratorio** cuyo
trabajo es *observar con verdad* el comportamiento de los modelos.

> **Nota de alcance:** este diseño **reemplaza el encuadre narrativo** previo del
> capítulo de pruebas (las 3 capas, los golden scenarios, `05-pruebas.tex`) como
> *historia* del capítulo. **No** descarta la infraestructura de código de
> `phase2-juan/benchmark/`, que se reutiliza.

## Decisiones tomadas (brainstorming)

1. **Qué se juzga:** la salida del **pipeline de lab completo**
   (Architect→sim→Tracker→Analyst→Reporter), con un **juez holístico único** y
   score/100. *(opción A)*
2. **Rúbrica:** 6 criterios mapeados 1:1 a los agentes (ver abajo).
3. **Cómo corre el juez:** **agéntico**, como Pablo. El harness exporta un
   `judge-bundle/`; Juan apunta **Codex** al bundle con un prompt de rúbrica y
   Codex escribe `llm-judge.md`. Independencia: lab sobre Claude, juez sobre
   Codex (otra familia). El harness **no** llama a Codex por API; entrega el
   prompt y las instrucciones de *qué decirle y cuándo*.
4. **Alcance de la run:** **un modelo representativo por paradigma** de CASO1
   (6 modelos), el **Architect genera el entorno** desde una descripción NL del
   dominio (elección dietética/valor). *(opción A)*
5. **Reutilización:** se reutiliza la infraestructura de `benchmark/` (runner
   e2e, `llm_meter`, check de tripleta joinable, agentes); solo se añade encima
   el export del bundle + el prompt de rúbrica. *(opción A)*

## Rúbrica (6 criterios)

Espejo de los 7 de Pablo, con sujeto = el lab:

1. **Fidelidad del entorno** (Architect) — ¿el env spec generado es coherente
   con el paradigma/modelo y permite observar su comportamiento?
2. **Fidelidad de observación** (Tracker) — ¿las trayectorias/eventos
   registrados reflejan fielmente la sim? Tripleta joinable (PG = denso =
   sparse, mismo `experiment_id`) y determinismo con semilla.
3. **Calidad del análisis** (Analyst) — ¿los patrones comportamiento-objetivo
   son correctos y están **anclados en los datos de la sim**, no inventados?
4. **Fidelidad del informe** (Reporter) — ¿el PDF es fiel a los datos (sin
   cifras alucinadas), bien fundamentado? (PDF real de tectonic, no fallback).
5. **Robustez del pipeline** — errores/warnings, determinismo, fallos de etapa.
6. **Juicio global** + **score/100**.

## Arquitectura — paralelismo con Pablo

| | **Pablo (Fase 1)** | **Fase 2 (este diseño)** |
|---|---|---|
| Sujeto | pipeline Researcher→Reasoner→Builder | lab Architect→sim→Tracker→Analyst→Reporter |
| Run | `eval run caso1` (corpus cerrado) | `run_lab_eval.py caso1` (6 modelos, 1/paradigma) |
| Métricas duras | `report.{json,md}` (KG, coste, latencia) | `report.{json,md}` (env spec, tripleta joinable, determinismo, coste/tokens/latencia, fallback PDF) |
| Bundle a juzgar | `artifact-bundle/` | `judge-bundle/` (env spec + trayectorias/Tracker + hallazgos Analyst + PDF Reporter) |
| Juez | Codex agéntico → `judge-reports/...-llm-judge.md` | igual: Codex agéntico → `llm-judge.md` |
| Rúbrica | 7 criterios, score/100 | 6 criterios, score/100 |
| Independencia | lab=Claude, juez=Codex | igual |

**Precondición:** el caso bajo evaluación está importado en OrbStack vía
`phase1-pablo/scripts/restore_eval_bundle.py` (CASO1 ya importado al 2026-06-30).
Modo "un caso cada vez": evaluar CASO1, luego resetear e importar+evaluar CASO2.

## Componentes (código)

Reutiliza `benchmark/`; añade:

- **`benchmark/run_lab_eval.py`** — runner principal. Generaliza `run_e2e.py` de
  2 modelos a **N modelos seleccionados**. Reutiliza tal cual: `MeteredClient`,
  `_Stage`, `_count_pg`/`_count_qdrant` (tripleta joinable), `is_fallback_report`
  y los agentes `Architect/Tracker/Analyst/Reporter`.
- **`benchmark/lab_report.py`** — calca `report.py` de Pablo:
  `render_markdown()` + `render_json()` + `write_report()`.
- **`benchmark/export_judge_bundle.py`** — escribe el `judge-bundle/`:
  `env_spec.json`, `trajectories/<modelo>.json`, `analyst_findings.md`,
  `report.pdf`, `metrics.json`. Autocontenido, rutas relativas.
- **`benchmark/JUDGE_PROMPT.md`** — plantilla del prompt de rúbrica (6 criterios)
  para Codex. Versionada en el repo.

**Selección de modelos:** patrón de `benchmark/model_keys.py` (`require_models`):
6 pares `paradigma/formulación` representativos de CASO1, resueltos vía
`discover_models`. Los 6 paradigmas de CASO1: `attribute-based-value-computation`,
`dlpfc-self-control-modulation`, `drift-diffusion-model`,
`goal-directed-vs-habitual-control`, `homeostatic-regulation-of-food-valuation`,
`pavlovian-control-of-food-approach`.

## Salida en disco (paralelo a Pablo)

```
benchmark/reports/2026-06-30-caso1-lab/
  report.json          # métricas duras
  report.md            # idem legible
  judge-bundle/        # lo que lee Codex
    env_spec.json
    trajectories/*.json
    analyst_findings.md
    report.pdf
    metrics.json
  JUDGE_PROMPT.md      # qué decirle a Codex (copia con rutas resueltas)
  llm-judge.md         # ← lo escribe Codex (Juan)
```

## Flujo de datos (`run_lab_eval.py`, semilla fija)

1. **Architect** genera el env spec desde NL del dominio de CASO1 →
   `env_spec.json`. *(criterio 1)*
2. Por cada uno de los 6 modelos: `discover_models`+`load_model`, simular K
   pasos con semilla → trayectorias. *(criterio 2)*
3. **Tracker** observa la sim → persiste la tripleta joinable → cuenta en cada
   store y comprueba `consistent`. *(criterios 2, 5)*
4. **Analyst** compara los 6 modelos → `analyst_findings.md`. *(criterio 3)*
5. **Reporter** → `report.pdf` + `is_fallback_report()`. *(criterio 4)*
6. `lab_report.py` vuelca `report.{json,md}`: env spec, conteos joinable +
   `consistent`, determinismo (semilla), coste/tokens/latencia por etapa
   (`MeteredClient`), flag fallback.

## El prompt del juez (`JUDGE_PROMPT.md`)

Calca el formato de Pablo:

- **Rol e independencia:** evaluador experto independiente; el lab corre sobre
  Claude, el juez es de otra familia (Codex). El trabajo del lab es **observar
  con verdad** el comportamiento de los modelos.
- **Verdad de referencia:** los **datos de la sim** (trayectorias/Tracker) son la
  verdad; los papers de CASO1 son contexto. Si un modelo se comporta de forma
  anómala y el lab lo reporta fielmente, el lab **acierta** (faithfulness, no
  corrección de la teoría).
- **Tarea:** leer los ficheros del `judge-bundle/` y citar rutas/datos concretos
  como evidencia.
- **Rúbrica (6 criterios):** por cada uno, juicio + evidencia citada.
- **Formato de salida** idéntico a Pablo: Veredicto · Tabla de evidencias ·
  Hallazgos por criterio · "Qué debe revisar un experto" · **Score/100**.
  Escribir en `llm-judge.md`.

**Cuándo lanzar Codex:** justo después de que `run_lab_eval.py` termine y exista
el `judge-bundle/`. Juan recibirá el comando/prompt exacto con rutas resueltas.

## Errores y tests

- **Errores:** ninguna etapa aborta la run. Un fallo (p. ej. Reporter cae a
  fallback) se registra en `report.json` (`failed_at`/flags) y el juez lo evalúa
  (criterio 5), igual que Pablo registra sus errores de KG.
- **Tests:** unit puro sin LLM para `lab_report.render_*` (result fixture →
  md/json esperados) y `export_judge_bundle` (estructura de ficheros). El runner
  es de integración (lo corre Juan, gasta LLM); **no** entra en la suite CI.

## Fuera de alcance (YAGNI)

- No se llama a Codex por API ni se automatiza el juez (Juan lo lanza a mano).
- No se calibra el juez con adversario/`RandomModel` ni jueces por dimensión
  (eso era del encuadre de 3 capas descartado; se mantiene el juez holístico
  único, como Pablo).
- No se toca `05-pruebas.tex` en este diseño; la redacción del capítulo es un
  paso posterior una vez existan los `llm-judge.md` de ambos casos.
- CASO2 se evalúa después, reseteando e importando su bundle (mismo runner).
