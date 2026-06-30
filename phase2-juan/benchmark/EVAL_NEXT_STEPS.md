# Eval de la Fase 2 (paralela a Pazos) — pendientes y prompt del juez

Estado al 2026-06-30: el armazón de evaluación está implementado y en `main`
(367 tests verdes). Lo que falta es **ejecutarlo en vivo** y el **juicio con
Codex** — ambos manuales porque gastan LLM y necesitan el backend.

Diseño y plan completos:
- `docs/superpowers/specs/2026-06-30-phase2-eval-migration-design.md`
- `docs/superpowers/plans/2026-06-30-phase2-eval-migration.md`

---

## Pendiente

### 1. CASO1 — run en vivo + juez (lo lanza Juan)
Precondición: backend arriba (`docker compose up -d` desde la raíz) y CASO1
importado en OrbStack (`cd phase1-pablo && uv run scripts/restore_eval_bundle.py
evals/reports/2026-06-29-caso1-pdf-corpus/artifact-bundle`).

```bash
cd phase2-juan
uv run python -m benchmark.run_lab_eval --case caso1
```
Produce `benchmark/reports/<fecha>-caso1-lab/` con `report.{json,md}`,
`judge-bundle/` y `JUDGE_PROMPT.md` (con `{BUNDLE_DIR}` ya resuelto). Al
terminar imprime el comando exacto de Codex.

Luego: lanzar Codex sobre el bundle (ver sección "Prompt a Codex"), que escribe
`llm-judge.md`. Después commitear el directorio del run + el veredicto:
```bash
git add phase2-juan/benchmark/reports/<fecha>-caso1-lab/
git commit -m "eval[phase2-eval]: CASO1 lab-eval run + Codex judge verdict"
```

### 2. CASO2 — cablear + importar + run + juez
**CASO2 todavía NO está cableado en el runner.** Antes de correrlo hay que
añadir una entrada `"caso2"` al dict `CASES` de
`benchmark/run_lab_eval.py`, análoga a `caso1`:
- `architect_prompt`: descripción NL del dominio de CASO2 (regulación
  homeostática / interocepción — ingesta, defensa de setpoint, reducción de
  drive).
- `keys` + `short`: un modelo representativo por paradigma de CASO2 (definir un
  `CASO2`/`CASO2_SHORT` en `benchmark/model_keys.py`, como se hizo con CASO1).

Después: resetear OrbStack e importar el bundle de CASO2 con
`restore_eval_bundle.py` (modo "un caso cada vez", wipe entre medias), y repetir
el run+juez con `--case caso2`.

### 3. Redacción de la memoria
Narrar la eval de Fase 2 en el capítulo de pruebas, paralela a la de Pazos
(run instrumentada + juez con rúbrica y score/100), con los resultados reales de
ambos casos. **No tocar `05-pruebas.tex` hasta tener los dos `llm-judge.md`.**

### Nota — ficheros ajenos sin commitear
Quedan modificados en el árbol, ajenos a este trabajo:
`benchmark/reports/e2e_metrics.json`, `docs/tfg-memoria-latex/capitulos/apendicee.tex`,
`docs/tfg-memoria-latex/figuras/ui-09-reporter-pdf.png` (+ `docs/.../tmp/` sin
trackear). Decidir aparte.

---

## Prompt a Codex (el juez)

El juez es **agéntico** (Codex, otra familia que el Claude del lab → independencia)
y lo lanzas tú. El runner ya escribe en cada run un `JUDGE_PROMPT.md` con
`{BUNDLE_DIR}` resuelto a la ruta absoluta del `judge-bundle/`. Comando que
imprime el runner:

```bash
cd benchmark/reports/<fecha>-caso1-lab/
codex exec "$(cat JUDGE_PROMPT.md)"
```

Codex debe leer el bundle y escribir el veredicto en
`benchmark/reports/<fecha>-caso1-lab/llm-judge.md`.

Plantilla del prompt (canónica en `benchmark/JUDGE_PROMPT.md`; `{BUNDLE_DIR}` se
sustituye por la ruta absoluta del bundle en cada run):

```markdown
# Evaluación experta del laboratorio virtual (Fase 2)

Eres un **evaluador experto independiente**. El laboratorio que vas a juzgar
corre sobre modelos Claude; tú eres de otra familia (Codex). Su tarea es
**observar con verdad** el comportamiento de unos modelos de decisión simulados
y comunicarlo (análisis + informe).

## Verdad de referencia
La **verdad** son los datos de la simulación: las trayectorias en
`{BUNDLE_DIR}/trajectories/*.json` (paso, acción, recompensa, estado interno).
Los papers del caso son contexto, no la vara de medir. Si un modelo se comporta
de forma anómala y el laboratorio lo reporta **fielmente**, el laboratorio
**acierta** — esto es un juicio de fidelidad/groundedness, no de si la teoría es
correcta.

## Material a revisar (léelo entero antes de puntuar)
- `{BUNDLE_DIR}/env_spec.json` — el entorno que generó el Architect.
- `{BUNDLE_DIR}/trajectories/*.json` — una trayectoria por modelo (ground truth).
- `{BUNDLE_DIR}/analyst_findings.md` — el análisis comparativo del Analyst.
- `{BUNDLE_DIR}/report.pdf` — el informe del Reporter (si existe).
- `{BUNDLE_DIR}/metrics.json` — métricas duras (tripleta joinable, determinismo,
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

## Formato de salida (escríbelo en `{BUNDLE_DIR}/../llm-judge.md`)
- **Veredicto** (una línea: pass / pass con reservas / fail).
- **Tabla de evidencias**: una fila por criterio (Criterio | Juicio | Ruta de evidencia).
- **Hallazgos por criterio**: un apartado por cada uno de los 6.
- **Qué debe revisar un experto manualmente**.
- **Score final: N/100** con una justificación breve.
```
