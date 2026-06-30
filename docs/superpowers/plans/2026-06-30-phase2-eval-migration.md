# Phase 2 Eval Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Pazos-parallel evaluation for the Phase 2 virtual lab: one instrumented run of the full lab pipeline over CASO1's models, plus an agentic LLM-judge (Codex) that scores it against a 6-criterion rubric.

**Architecture:** Generalize the existing `benchmark/run_e2e.py` from a 2-model run into `benchmark/run_lab_eval.py` that runs N representative models (one per CASO1 paradigm) through Architect→sim→Tracker→Analyst→Reporter. It emits hard metrics (`report.{json,md}`), a self-contained `judge-bundle/` for the judge to read, and a resolved `JUDGE_PROMPT.md`. Juan then points Codex at the bundle; Codex writes `llm-judge.md`. Reuses `MeteredClient`, the joinable-triple counters, `is_fallback_report`, and all five agents unchanged.

**Tech Stack:** Python 3.13, `uv`, pytest, SQLAlchemy async, OpenRouter (Claude) for the lab, Codex (run manually by Juan) for the judge. Backend stack in OrbStack with CASO1 already imported via `phase1-pablo/scripts/restore_eval_bundle.py`.

## Global Constraints

- All commands run from `phase2-juan/` with the backend up and `.env` present.
- Tests run with `uv run pytest`; new unit tests live under `phase2-juan/tests/` and must be LLM-free (no network) so they stay in CI.
- The integration runner (`run_lab_eval.py`) makes real LLM/embedding calls; it is run manually by Juan and is NOT added to CI.
- Reuse existing helpers; do not duplicate `MeteredClient`, `_count_pg`, `_count_qdrant`, `is_fallback_report`, or agent code.
- Spanish for user-facing report/prompt text (matches the repo's memoria language).
- Judge model is Codex (different family from the lab's Claude) — independence is a design property; the runner never calls Codex.

---

### Task 1: CASO1 representative model keys

**Files:**
- Modify: `phase2-juan/benchmark/model_keys.py` (append)
- Test: `phase2-juan/tests/test_caso_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CASO1: list[str]` (6 `"paradigm/formulation"` keys) and `CASO1_SHORT: dict[str, str]` (short labels) in `benchmark.model_keys`.

- [ ] **Step 1: Write the failing test**

```python
# phase2-juan/tests/test_caso_models.py
from benchmark.model_keys import CASO1, CASO1_SHORT


def test_caso1_has_one_model_per_paradigm():
    assert len(CASO1) == 6
    paradigms = [k.split("/")[0] for k in CASO1]
    assert len(set(paradigms)) == 6, f"expected 6 distinct paradigms, got {paradigms}"
    assert all(k.count("/") == 1 for k in CASO1)


def test_caso1_short_labels_cover_every_key():
    assert set(CASO1_SHORT) == set(CASO1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_caso_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'CASO1'`.

- [ ] **Step 3: Append the keys to `model_keys.py`**

```python
# Append to phase2-juan/benchmark/model_keys.py

# CASO1 (decisión basada en valor / neuroeconomía) — one representative
# formulation per paradigm. For drift-diffusion-model we use the Wiener-process
# formulation, not collapsing-boundary: Pazos's own LLM judge flagged the
# collapsing-boundary row as pointing at the wrong class.
CASO1 = [
    "attribute-based-value-computation/weighted-linear-summation-with-state-dependent-attribute-weights-algebraic",
    "dlpfc-self-control-modulation/attribute-reweighting-algebraic-model",
    "drift-diffusion-model/classical-wiener-process-with-per-action-accumulators",
    "goal-directed-vs-habitual-control/dual-q-table-with-fixed-exponential-decay-arbitration",
    "homeostatic-regulation-of-food-valuation/drive-reduction-ode-with-goal-directed-valuation",
    "pavlovian-control-of-food-approach/rescorlawagner-cached-value-agent-with-softmax-action-selection",
]

CASO1_SHORT = {
    CASO1[0]: "Valor por atributos (algebraico)",
    CASO1[1]: "Autocontrol dlPFC (reponderación)",
    CASO1[2]: "DDM (Wiener)",
    CASO1[3]: "Dirigido vs hábito (Q dual)",
    CASO1[4]: "Homeostasis (drive-reduction ODE)",
    CASO1[5]: "Pavloviano (Rescorla-Wagner softmax)",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_caso_models.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/benchmark/model_keys.py phase2-juan/tests/test_caso_models.py
git commit -m "feat[phase2-eval]: CASO1 representative model keys (one per paradigm)"
```

---

### Task 2: Hard-metrics report renderer (`lab_report.py`)

**Files:**
- Create: `phase2-juan/benchmark/lab_report.py`
- Test: `phase2-juan/tests/test_lab_report.py`

**Interfaces:**
- Consumes: a `result: dict` shaped like the example `SAMPLE` below (produced by the runner in Task 5).
- Produces:
  - `render_json(result: dict) -> str`
  - `render_markdown(result: dict) -> str`
  - `write_report(result: dict, out_dir: Path) -> tuple[Path, Path]` returning `(json_path, md_path)`.

- [ ] **Step 1: Write the failing test**

```python
# phase2-juan/tests/test_lab_report.py
import json

from benchmark.lab_report import render_json, render_markdown, write_report

SAMPLE = {
    "case": "caso1",
    "seed": 42,
    "steps": 60,
    "env_spec": {
        "grid": {"width": 8, "height": 8},
        "actions": ["move_up", "eat", "stay"],
        "resources": [{"type": "food", "count": 6, "regenerate": True}],
    },
    "models": [
        {"key": "drift-diffusion-model/x", "short": "DDM (Wiener)",
         "events": 60, "total_reward": 7.0, "final_state_keys": ["v", "a"]},
        {"key": "homeostatic-regulation-of-food-valuation/y",
         "short": "Homeostasis", "events": 60, "total_reward": 5.0,
         "final_state_keys": ["energy_reserves"]},
    ],
    "joinable_triple": {
        "written": 6, "postgres_rows": 6, "qdrant_dense": 6,
        "qdrant_sparse": 6, "consistent": True, "episodes_filtered": 0,
    },
    "determinism": {"key": "drift-diffusion-model/x", "identical": True},
    "reporter": {"pdf_key": "experiments/e/report.pdf",
                 "pdf_produced": True, "pdf_is_real_latex": True},
    "latency_per_stage": {
        "architect": {"seconds": 3.0, "input_tokens": 10, "output_tokens": 5},
    },
    "usage": {"input_tokens": 100, "output_tokens": 20, "calls": 3,
              "seconds": 5.0, "estimated_cost_usd": 0.0123},
    "total_seconds": 42.0,
}


def test_render_json_roundtrips():
    assert json.loads(render_json(SAMPLE)) == SAMPLE


def test_render_markdown_has_key_sections():
    md = render_markdown(SAMPLE)
    assert "caso1" in md
    assert "DDM (Wiener)" in md            # per-model table
    assert "Homeostasis" in md
    assert "consistent" in md.lower() or "joinable" in md.lower()
    assert "0.0123" in md                  # estimated cost surfaced
    assert "determin" in md.lower()        # determinism section present


def test_write_report_creates_both_files(tmp_path):
    json_path, md_path = write_report(SAMPLE, tmp_path)
    assert json_path.name == "report.json"
    assert md_path.name == "report.md"
    assert json.loads(json_path.read_text()) == SAMPLE
    assert "caso1" in md_path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_lab_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.lab_report'`.

- [ ] **Step 3: Write the implementation**

```python
# phase2-juan/benchmark/lab_report.py
"""Render a lab-eval ``result`` dict as Markdown + JSON for benchmark/reports/.

Parallel to phase1's ``decisionlab.eval.report``: hard, reproducible metrics
from one instrumented run of the Phase 2 lab pipeline. No LLM, no judgement —
the verdict is the judge's job (see JUDGE_PROMPT.md).
"""

from __future__ import annotations

import json
from pathlib import Path


def render_json(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def render_markdown(result: dict) -> str:
    env = result.get("env_spec", {})
    grid = env.get("grid", {})
    jt = result.get("joinable_triple", {})
    det = result.get("determinism", {})
    rep = result.get("reporter", {})
    usage = result.get("usage", {})

    lines: list[str] = []
    lines.append(f"# Lab eval — `{result.get('case', '?')}`")
    lines.append("")
    lines.append(
        f"_seed_: {result.get('seed')} · _steps_: {result.get('steps')} · "
        f"_total_: {result.get('total_seconds')} s · "
        f"_coste estimado_: ${usage.get('estimated_cost_usd')}"
    )
    lines.append("")

    lines.append("## Entorno (Architect)")
    lines.append(
        f"Rejilla {grid.get('width')}x{grid.get('height')} · "
        f"acciones: {', '.join(env.get('actions', []))}"
    )
    for r in env.get("resources", []):
        lines.append(
            f"- recurso `{r.get('type')}` x{r.get('count')} "
            f"(regenera: {r.get('regenerate')})"
        )
    lines.append("")

    lines.append("## Modelos simulados")
    lines.append("| Modelo | key | eventos | recompensa total |")
    lines.append("|---|---|---:|---:|")
    for m in result.get("models", []):
        lines.append(
            f"| {m.get('short')} | `{m.get('key')}` | "
            f"{m.get('events')} | {m.get('total_reward')} |"
        )
    lines.append("")

    lines.append("## Fidelidad de observación (Tracker)")
    lines.append(
        f"Tripleta joinable — escritas {jt.get('written')}, "
        f"PG {jt.get('postgres_rows')}, denso {jt.get('qdrant_dense')}, "
        f"sparse {jt.get('qdrant_sparse')} → **consistent={jt.get('consistent')}**"
    )
    lines.append("")

    lines.append("## Determinismo")
    lines.append(
        f"Re-simulación de `{det.get('key')}` con la misma semilla → "
        f"trayectoria idéntica: **{det.get('identical')}**"
    )
    lines.append("")

    lines.append("## Informe (Reporter)")
    lines.append(
        f"PDF producido: {rep.get('pdf_produced')} · "
        f"PDF real de LaTeX (no fallback): **{rep.get('pdf_is_real_latex')}**"
    )
    lines.append("")

    lines.append("## Coste y latencia")
    lines.append(
        f"Tokens in/out: {usage.get('input_tokens')}/{usage.get('output_tokens')} · "
        f"llamadas: {usage.get('calls')} · coste estimado: "
        f"${usage.get('estimated_cost_usd')}"
    )
    lines.append("")
    lines.append("| Etapa | s | in tok | out tok |")
    lines.append("|---|---:|---:|---:|")
    for stage, d in result.get("latency_per_stage", {}).items():
        lines.append(
            f"| {stage} | {d.get('seconds')} | "
            f"{d.get('input_tokens')} | {d.get('output_tokens')} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(result: dict, out_dir: Path) -> tuple[Path, Path]:
    """Write report.json + report.md into out_dir. Returns the two paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(render_json(result))
    md_path.write_text(render_markdown(result))
    return json_path, md_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_lab_report.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/benchmark/lab_report.py phase2-juan/tests/test_lab_report.py
git commit -m "feat[phase2-eval]: hard-metrics report renderer for lab eval"
```

---

### Task 3: Judge-bundle exporter (`export_judge_bundle.py`)

**Files:**
- Create: `phase2-juan/benchmark/export_judge_bundle.py`
- Test: `phase2-juan/tests/test_export_judge_bundle.py`

**Interfaces:**
- Consumes: outputs assembled by the runner (Task 5).
- Produces: `export_judge_bundle(out_dir: Path, *, env_spec: dict, trajectories: dict[str, list[dict]], analyst_findings: str, report_pdf: bytes | None, metrics: dict) -> Path` returning the created `judge-bundle/` path. Model keys in `trajectories` have their `/` replaced by `_` in filenames.

- [ ] **Step 1: Write the failing test**

```python
# phase2-juan/tests/test_export_judge_bundle.py
import json

from benchmark.export_judge_bundle import export_judge_bundle


def test_export_bundle_structure(tmp_path):
    bundle = export_judge_bundle(
        tmp_path,
        env_spec={"grid": {"width": 8, "height": 8}},
        trajectories={
            "drift-diffusion-model/x": [
                {"step": 0, "action": "eat", "reward": 1.0, "state": {"v": 0.2}}
            ]
        },
        analyst_findings="## Hallazgos\nLos modelos difieren.",
        report_pdf=b"%PDF-1.5 fake",
        metrics={"case": "caso1", "seed": 42},
    )
    assert bundle.name == "judge-bundle"
    assert json.loads((bundle / "env_spec.json").read_text())["grid"]["width"] == 8
    traj = json.loads((bundle / "trajectories" / "drift-diffusion-model_x.json").read_text())
    assert traj[0]["action"] == "eat"
    assert (bundle / "analyst_findings.md").read_text().startswith("## Hallazgos")
    assert (bundle / "report.pdf").read_bytes() == b"%PDF-1.5 fake"
    assert json.loads((bundle / "metrics.json").read_text())["seed"] == 42


def test_export_bundle_omits_pdf_when_none(tmp_path):
    bundle = export_judge_bundle(
        tmp_path,
        env_spec={},
        trajectories={},
        analyst_findings="x",
        report_pdf=None,
        metrics={},
    )
    assert not (bundle / "report.pdf").exists()
    assert (bundle / "trajectories").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export_judge_bundle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'benchmark.export_judge_bundle'`.

- [ ] **Step 3: Write the implementation**

```python
# phase2-juan/benchmark/export_judge_bundle.py
"""Export one lab-eval run as a self-contained ``judge-bundle/``.

The bundle is what the (agentic, Codex) judge reads — parallel to Pazos's
``artifact-bundle/``. It holds the lab's outputs grouped by what each rubric
criterion needs: the Architect's env spec, per-model trajectories (the ground
truth for observation/analysis), the Analyst's findings, the Reporter's PDF,
and a copy of the hard metrics.
"""

from __future__ import annotations

import json
from pathlib import Path


def export_judge_bundle(
    out_dir: Path,
    *,
    env_spec: dict,
    trajectories: dict[str, list[dict]],
    analyst_findings: str,
    report_pdf: bytes | None,
    metrics: dict,
) -> Path:
    bundle = out_dir / "judge-bundle"
    (bundle / "trajectories").mkdir(parents=True, exist_ok=True)

    (bundle / "env_spec.json").write_text(
        json.dumps(env_spec, indent=2, ensure_ascii=False)
    )
    for key, records in trajectories.items():
        safe = key.replace("/", "_")
        (bundle / "trajectories" / f"{safe}.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False)
        )
    (bundle / "analyst_findings.md").write_text(analyst_findings)
    (bundle / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False)
    )
    if report_pdf is not None:
        (bundle / "report.pdf").write_bytes(report_pdf)
    return bundle
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export_judge_bundle.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/benchmark/export_judge_bundle.py phase2-juan/tests/test_export_judge_bundle.py
git commit -m "feat[phase2-eval]: judge-bundle exporter"
```

---

### Task 4: Judge rubric prompt (`JUDGE_PROMPT.md`)

**Files:**
- Create: `phase2-juan/benchmark/JUDGE_PROMPT.md`
- Test: `phase2-juan/tests/test_judge_prompt.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a committed prompt template containing the literal placeholder `{BUNDLE_DIR}` (the runner substitutes the resolved absolute path in Task 5) and the 6 rubric criteria.

- [ ] **Step 1: Write the failing test**

```python
# phase2-juan/tests/test_judge_prompt.py
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "benchmark" / "JUDGE_PROMPT.md"


def test_prompt_has_placeholder_and_six_criteria():
    text = PROMPT.read_text().lower()
    assert "{bundle_dir}" in text
    for kw in ("entorno", "observación", "análisis", "informe", "robustez", "global"):
        assert kw in text, f"missing rubric criterion keyword: {kw}"
    assert "/100" in text
    assert "llm-judge.md" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_judge_prompt.py -v`
Expected: FAIL with `FileNotFoundError` (prompt file absent).

- [ ] **Step 3: Write the prompt file**

```markdown
<!-- phase2-juan/benchmark/JUDGE_PROMPT.md -->
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_judge_prompt.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/benchmark/JUDGE_PROMPT.md phase2-juan/tests/test_judge_prompt.py
git commit -m "feat[phase2-eval]: judge rubric prompt (6 criteria) for Codex"
```

---

### Task 5: Lab-eval runner (`run_lab_eval.py`)

**Files:**
- Create: `phase2-juan/benchmark/run_lab_eval.py`
- Reference (do not modify): `phase2-juan/benchmark/run_e2e.py:70-309` (pattern source)

**Interfaces:**
- Consumes: `CASO1`, `CASO1_SHORT` (Task 1); `render_json`/`write_report` (Task 2); `export_judge_bundle` (Task 3); `benchmark/JUDGE_PROMPT.md` (Task 4); existing `MeteredClient`, `_Stage`, `_count_pg`, `_count_qdrant` semantics from `run_e2e.py` (copy the two `_count_*` helpers and `_Stage` into this module — they are small and private to the runner; do not import from `run_e2e`).
- Produces: a CLI `uv run python -m benchmark.run_lab_eval [--case caso1]` that writes `benchmark/reports/<YYYY-MM-DD>-<case>-lab/{report.json,report.md,judge-bundle/,JUDGE_PROMPT.md}` and prints the exact Codex instruction.

This task has no unit test (it makes real LLM/embedding calls). Its deliverable is verified by a manual run (Step 3) against the OrbStack stack with CASO1 imported.

- [ ] **Step 1: Write the runner**

```python
# phase2-juan/benchmark/run_lab_eval.py
"""Instrumented run of the full Phase 2 lab over one closed-corpus case.

Parallel to Pazos's ``eval run``: drives Architect → simulation → Tracker →
Knowledge-Backbone write → Analyst → Reporter over one representative model per
paradigm, records hard metrics, and exports a ``judge-bundle/`` plus a resolved
``JUDGE_PROMPT.md``. An agentic judge (Codex, run by Juan) then writes
``llm-judge.md``. Reuses the simlab agents and the e2e metering pattern.

Usage (from phase2-juan/, backend up, .env present, case imported in OrbStack)::

    uv run python -m benchmark.run_lab_eval --case caso1
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import random
import time
import uuid
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from simlab.analyst import Analyst
from simlab.architect import Architect
from simlab.critical_events import critical_events_to_json, detect_critical_events
from simlab.environment import Agent, Position
from simlab.knowledge import ModelInfo, SimulationContext, build_writer_from_services
from simlab.model_loader import discover_models, load_model
from simlab.reporter import Reporter
from simlab.spec import spec_to_environment
from simlab.tracker import Tracker

from benchmark.export_judge_bundle import export_judge_bundle
from benchmark.faithfulness import is_fallback_report
from benchmark.lab_report import write_report
from benchmark.llm_meter import MeteredClient
from benchmark.model_keys import CASO1, CASO1_SHORT, REPORTS, require_models
from shared.services import init_services, shutdown_services

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SEED = 42
STEPS = 60

# Per-case Architect brief + the model keys to simulate.
CASES: dict[str, dict] = {
    "caso1": {
        "keys": CASO1,
        "short": CASO1_SHORT,
        "architect_prompt": (
            "Diseña un entorno de rejilla 8x8 para estudiar la elección dietética "
            "basada en valor. Debe haber recursos de tipo 'food' (al menos 6 "
            "unidades que regeneran al consumirse), cada uno con atributos de "
            "valor observables, en particular 'palatability' y 'health'. Las "
            "acciones disponibles son: move_up, move_down, move_left, move_right "
            "(mover una celda), eat (consume comida en la celda actual, recompensa "
            "según su valor) y stay. Devuelve la especificación del entorno."
        ),
    },
}


class _Stage:
    """Times a stage and snapshots the metered token delta around it."""

    def __init__(self, name: str, usage, sink: dict) -> None:
        self.name, self.usage, self.sink = name, usage, sink

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._in0 = self.usage.input_tokens
        self._out0 = self.usage.output_tokens
        return self

    def __exit__(self, *exc):
        self.sink[self.name] = {
            "seconds": round(time.perf_counter() - self._t0, 2),
            "input_tokens": self.usage.input_tokens - self._in0,
            "output_tokens": self.usage.output_tokens - self._out0,
        }
        return False


async def _count_qdrant(vectors, collection: str, exp_id: str) -> int | None:
    try:
        from qdrant_client import models as qm

        res = await vectors._c().count(
            collection_name=collection,
            count_filter=qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="phase2_experiment_id",
                        match=qm.MatchValue(value=exp_id),
                    )
                ]
            ),
            exact=True,
        )
        return res.count
    except Exception:
        return None


async def _count_pg(db, exp_id: str) -> int:
    from sqlalchemy import func, select

    from shared.models import SimulationObservation

    async with db.get_session() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(SimulationObservation)
                .where(SimulationObservation.phase2_experiment_id == exp_id)
            )
        ).scalar_one()


def _trajectory_for(events: list, agent_id: str) -> list[dict]:
    """Per-agent step records (the judge's ground truth), mirroring StepRecord."""
    return [
        {
            "step": ev.step,
            "action": ev.action.name,
            "reward": float(ev.outcome.get("reward", 0.0)),
            "state": ev.outcome.get("model_state", {}),
        }
        for ev in events
        if ev.agent_id == agent_id
    ]


def _build_env(spec: dict):
    return spec_to_environment(spec, seed=SEED)


async def _simulate(spec: dict, keys, models, storage):
    """Build a fresh env, add one agent per model, run STEPS. Returns
    (events, agent_to_model, agent_ids_by_key)."""
    env = _build_env(spec)
    rng = random.Random(SEED)
    agent_to_model: dict[str, ModelInfo] = {}
    agent_ids_by_key: dict[str, str] = {}
    for key in keys:
        info = models[key]
        model = await load_model(info, storage=storage, seed=SEED)
        agent_id = info.formulation
        env.add_agent(
            Agent(
                id=agent_id,
                position=Position(
                    rng.randint(0, env.width - 1), rng.randint(0, env.height - 1)
                ),
                decision_model=model,
            )
        )
        agent_to_model[agent_id] = ModelInfo(
            model_id=info.id,
            class_name=info.class_name,
            paradigm=info.paradigm,
            formulation=info.formulation,
            phase1_run_id=info.run_id,
        )
        agent_ids_by_key[key] = agent_id
    events = env.run(STEPS)
    return env, events, agent_to_model, agent_ids_by_key


async def main(case: str) -> None:
    if case not in CASES:
        raise SystemExit(f"caso desconocido: {case}. Disponibles: {sorted(CASES)}")
    cfg = CASES[case]
    keys = cfg["keys"]

    t_start = time.perf_counter()
    svc = await init_services()
    writer = build_writer_from_services(svc)
    if writer is not None:
        svc = dataclasses.replace(svc, sim_memory_writer=writer)

    client = MeteredClient(anthropic.AsyncAnthropic(timeout=180.0))
    exp_id = str(uuid.uuid4())
    stages: dict = {}
    result: dict = {"case": case, "experiment_id": exp_id, "seed": SEED, "steps": STEPS}
    env_spec_full: dict = {}
    trajectories: dict[str, list[dict]] = {}
    analyst_output = ""
    report_pdf: bytes | None = None

    try:
        models = await discover_models(db=svc.db)
        require_models(models, keys)

        # 1. Architect → environment spec
        architect = Architect(client=client)
        with _Stage("architect", client.usage, stages):
            spec_json = await architect.run(cfg["architect_prompt"], max_iterations=6)
        spec = json.loads(spec_json)
        env_spec_full = spec

        from shared.models import Experiment as DBExperiment

        async with svc.db.get_session() as session:
            session.add(
                DBExperiment(
                    id=uuid.UUID(exp_id),
                    description=f"lab eval: {case}",
                    status="created",
                    spec=spec,
                )
            )
            await session.commit()

        result["env_spec"] = {
            "grid": spec.get("grid"),
            "actions": [a["name"] for a in spec.get("actions", [])],
            "resources": [
                {"type": r["type"], "count": r.get("count"),
                 "regenerate": r.get("regenerate")}
                for r in spec.get("resources", [])
            ],
        }

        # 2. Simulate one model per paradigm (no LLM)
        with _Stage("simulation", client.usage, stages):
            env, all_events, agent_to_model, agent_ids_by_key = await _simulate(
                spec, keys, models, svc.storage
            )
        critical = critical_events_to_json(detect_critical_events(all_events))
        result["events"] = len(all_events)

        models_summary = []
        for key in keys:
            agent_id = agent_ids_by_key[key]
            traj = _trajectory_for(all_events, agent_id)
            trajectories[key] = traj
            models_summary.append(
                {
                    "key": key,
                    "short": cfg["short"].get(key, key),
                    "events": len(traj),
                    "total_reward": round(sum(r["reward"] for r in traj), 3),
                    "final_state_keys": list(traj[-1]["state"]) if traj else [],
                }
            )
        result["models"] = models_summary

        # 2b. Determinism check: re-simulate the first model, compare trajectory
        _, ev2, _, ids2 = await _simulate(spec, keys[:1], models, svc.storage)
        rerun = _trajectory_for(ev2, ids2[keys[0]])
        result["determinism"] = {
            "key": keys[0],
            "identical": rerun == trajectories[keys[0]],
        }

        # 3. Tracker
        tracker = Tracker(client=client)
        with _Stage("tracker", client.usage, stages):
            tracker_output = await tracker.run(
                "Observa la simulación y reporta trayectorias y episodios clave.",
                all_events,
                critical_events=critical,
            )

        # 4. Persist the joinable triple, then count it in each store
        if svc.sim_memory_writer is not None:
            ctx = SimulationContext(
                phase2_experiment_id=exp_id,
                environment=f"grid_{env.width}x{env.height}",
                steps=STEPS,
                seed=SEED,
                agent_to_model=agent_to_model,
            )
            with _Stage("kg_write", client.usage, stages):
                wr = await svc.sim_memory_writer.write(tracker_output, ctx)
            written = (
                wr.summaries_written + wr.trajectories_written + wr.episodes_written
            )
            pg = await _count_pg(svc.db, exp_id)
            dense = await _count_qdrant(svc.vectors, "memories_dense", exp_id)
            sparse = await _count_qdrant(svc.vectors, "memories_sparse", exp_id)
            result["joinable_triple"] = {
                "written": written,
                "postgres_rows": pg,
                "qdrant_dense": dense,
                "qdrant_sparse": sparse,
                "consistent": (pg == written == dense == sparse),
                "episodes_filtered": wr.episodes_filtered,
            }
        else:
            result["joinable_triple"] = {"skipped": "no sim_memory_writer"}

        # 5. Analyst
        analyst = Analyst(client=client, storage=svc.storage, db=svc.db)
        charts: list[dict] = []
        with _Stage("analyst", client.usage, stages):
            analyst_output = await analyst.run(
                "Compara los modelos: patrones de comportamiento, episodios "
                "críticos y relación entre acciones, recompensas y estado interno.",
                tracker_output,
                all_events,
                experiment_id=exp_id,
                charts_accumulator=charts,
                critical_events=critical,
                max_iterations=8,
            )
        result["charts_generated"] = len(charts)

        # 6. Reporter
        reporter = Reporter(client=client, storage=svc.storage, db=svc.db)
        try:
            with _Stage("reporter", client.usage, stages):
                await reporter.run(
                    "Genera un informe del experimento comparando los modelos.",
                    tracker_output,
                    analyst_output,
                    run_id=models[keys[0]].run_id or "",
                    experiment_id=exp_id,
                    charts=charts,
                )
        except Exception as exc:
            result["reporter_error"] = f"{type(exc).__name__}: {exc}"
        pdf_key = reporter.last_pdf_key
        pdf_real = None
        if pdf_key:
            report_pdf = await svc.storage.get(pdf_key)
            producer_fallback = b"matplotlib" in report_pdf.lower()
            tex_bytes = await svc.storage.get(f"experiments/{exp_id}/report.tex")
            banner_fallback = is_fallback_report(tex_bytes.decode("utf-8", "ignore"))
            pdf_real = not (producer_fallback or banner_fallback)
        result["reporter"] = {
            "pdf_key": pdf_key,
            "pdf_produced": pdf_key is not None,
            "pdf_is_real_latex": pdf_real,
        }

    finally:
        await shutdown_services(svc)

    result["latency_per_stage"] = stages
    result["total_seconds"] = round(time.perf_counter() - t_start, 2)
    result["usage"] = client.usage.as_dict()

    # Write report + bundle + resolved prompt
    out_dir = REPORTS / f"{date.today().isoformat()}-{case}-lab"
    write_report(result, out_dir)
    bundle = export_judge_bundle(
        out_dir,
        env_spec=env_spec_full,
        trajectories=trajectories,
        analyst_findings=analyst_output or "(sin salida del Analyst)",
        report_pdf=report_pdf,
        metrics=result,
    )
    prompt_template = (
        Path(__file__).resolve().parent / "JUDGE_PROMPT.md"
    ).read_text()
    resolved = prompt_template.replace("{BUNDLE_DIR}", str(bundle.resolve()))
    (out_dir / "JUDGE_PROMPT.md").write_text(resolved)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n" + "=" * 70)
    print("Run del lab completa. Para el juicio, ejecuta Codex así:\n")
    print(f"  cd {bundle.resolve().parent}")
    print(f"  codex exec \"$(cat JUDGE_PROMPT.md)\"")
    print(f"\nCodex debe escribir el veredicto en: {out_dir.resolve()}/llm-judge.md")
    print("=" * 70)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="caso1")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().case))
```

- [ ] **Step 2: Verify the module imports cleanly (no LLM)**

Run: `uv run python -c "import benchmark.run_lab_eval as r; print(sorted(r.CASES))"`
Expected: prints `['caso1']` with no import error.

- [ ] **Step 3: Manual integration run (Juan, backend up + CASO1 imported)**

Run: `uv run python -m benchmark.run_lab_eval --case caso1`
Expected: completes (several minutes, real LLM cost); prints the metrics JSON and a Codex instruction block. Confirm these exist:

```bash
ls benchmark/reports/$(date +%F)-caso1-lab/
# report.json  report.md  judge-bundle/  JUDGE_PROMPT.md
ls benchmark/reports/$(date +%F)-caso1-lab/judge-bundle/
# analyst_findings.md  env_spec.json  metrics.json  report.pdf  trajectories/
```

Sanity-check `report.json`: `joinable_triple.consistent` should be `true` and `reporter.pdf_is_real_latex` should be `true` (if either is false, that is a real finding for the judge, not a plan failure — record it and continue).

- [ ] **Step 4: Commit**

```bash
git add phase2-juan/benchmark/run_lab_eval.py
git commit -m "feat[phase2-eval]: lab-eval runner (Architect→...→Reporter, bundle + prompt)"
```

---

### Task 6: Run the judge and capture the verdict (Juan + Codex)

**Files:**
- Create (by Codex): `phase2-juan/benchmark/reports/<date>-caso1-lab/llm-judge.md`

This task is manual and produces the judge artifact. No code.

- [ ] **Step 1: Run Codex against the bundle**

From the directory printed by Task 5 Step 3, run the Codex command it printed (`codex exec "$(cat JUDGE_PROMPT.md)"`). Codex reads the bundle and writes `llm-judge.md` with: verdict, evidence table, findings per criterion, "what an expert should review", and a score/100.

- [ ] **Step 2: Verify the verdict file**

```bash
test -s benchmark/reports/$(date +%F)-caso1-lab/llm-judge.md && echo OK
```
Expected: `OK`, and the file contains a `/100` score and the 6 criteria.

- [ ] **Step 3: Commit**

```bash
git add phase2-juan/benchmark/reports/$(date +%F)-caso1-lab/
git commit -m "eval[phase2-eval]: CASO1 lab-eval run + Codex judge verdict"
```

---

## Self-Review

**Spec coverage:**
- Run of full lab pipeline, one judge, score/100 → Tasks 5 + 6. ✓
- 6-criterion rubric → Task 4 (`JUDGE_PROMPT.md`) + asserted in test. ✓
- Agentic Codex judge, independence, Juan runs it → Tasks 4/5/6 (runner emits instruction; no API call). ✓
- One representative model per paradigm, Architect generates env → Tasks 1 + 5. ✓
- Reuse benchmark/ infra (MeteredClient, joinable counters, is_fallback_report, agents) → Task 5. ✓
- Hard-metrics report.{json,md} parallel to Pablo → Task 2. ✓
- judge-bundle/ parallel to artifact-bundle → Task 3. ✓
- Disk layout (report.* + judge-bundle/ + JUDGE_PROMPT.md + llm-judge.md) → Tasks 5/6. ✓
- Errors don't abort; recorded for the judge → Task 5 (reporter_error capture, pdf_real flag). ✓
- Unit tests LLM-free, runner is manual integration → Tasks 2/3/4 unit; Task 5/6 manual. ✓
- CASO2 later via reset+import, same runner → CASES dict is extensible (out of scope now, noted). ✓

**Placeholder scan:** No TBD/TODO. All code blocks complete; test bodies concrete. `{BUNDLE_DIR}` is an intentional template token, not a plan placeholder.

**Type consistency:** `result` dict shape in Task 2's `SAMPLE` matches what Task 5 assembles (case, seed, steps, env_spec, models[], joinable_triple, determinism, reporter, latency_per_stage, usage, total_seconds). `export_judge_bundle` signature identical in Task 3 def and Task 5 call. `CASO1`/`CASO1_SHORT` defined in Task 1, consumed in Task 5. `_trajectory_for` record shape (`step/action/reward/state`) matches `StepRecord` and the bundle test in Task 3.
