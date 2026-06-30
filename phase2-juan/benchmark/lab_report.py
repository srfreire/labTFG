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
