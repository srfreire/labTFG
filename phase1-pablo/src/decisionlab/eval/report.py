"""Render a ``SuiteResult`` as Markdown and JSON for evals/reports/."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from decisionlab.eval.suite import SuiteResult


def render_markdown(result: SuiteResult) -> str:
    """Human-readable suite report. One section per topic with a status
    table; KG growth and cost summarised at the bottom."""
    spec = result.suite
    lines: list[str] = []
    lines.append(f"# Eval suite: `{spec.name}`")
    lines.append("")

    if spec.source_path is not None:
        lines.append(f"_Source_: `{spec.source_path}`")
    lines.append(f"_Stages_: `{', '.join(s.value for s in spec.stages)}`")
    lines.append(f"_Topics_: {len(spec.topics)} declared, {result.topics_run()} run")
    lines.append(f"_Duration_: {result.duration_ms / 1000:.1f}s")
    lines.append(f"_Cost (est.)_: ${result.total_usd:.2f}")
    if result.budget_exhausted:
        lines.append("> **Budget exhausted — not all topics ran.**")
    if result.error:
        lines.append(f"> **Suite error**: {result.error}")
    lines.append("")
    lines.append(f"**Overall**: {'PASS' if result.all_passed else 'FAIL'}")
    lines.append("")

    # KG growth
    if result.pre_stats and result.post_stats:
        lines.append("## KG growth")
        lines.append("")
        lines.append("| | Before | After | Δ |")
        lines.append("|---|---:|---:|---:|")
        lines.append(
            f"| Nodes | {result.pre_stats.total_nodes} | "
            f"{result.post_stats.total_nodes} | "
            f"{result.post_stats.total_nodes - result.pre_stats.total_nodes:+d} |"
        )
        lines.append(
            f"| Relations | {result.pre_stats.total_relations} | "
            f"{result.post_stats.total_relations} | "
            f"{result.post_stats.total_relations - result.pre_stats.total_relations:+d} |"
        )
        lines.append("")

    # Per-topic
    for tr in result.topic_results:
        lines.append(f"## Topic: {tr.topic}")
        run = tr.run
        status = "ok" if run.succeeded else f"failed at {run.failed_at} — {run.error}"
        lines.append(f"_run_: `{run.run_id}` — _{status}_")
        if run.paradigms:
            lines.append(f"_paradigms_: {', '.join(run.paradigms)}")
        lines.append("")
        if run.memory_per_stage:
            lines.append("**Memory writes**:")
            for stage_name, payload in run.memory_per_stage.items():
                lines.append(
                    f"- `{stage_name}` — "
                    f"nodes_created={payload.get('nodes_created', 0)}, "
                    f"relations_created={payload.get('relations_created', 0)}, "
                    f"facts={payload.get('facts_stored', 0)}"
                )
            lines.append("")
        if tr.assertions:
            lines.append("**Assertions**:")
            lines.append("")
            lines.append("| Stage | Predicate | Result | Detail |")
            lines.append("|---|---|:-:|---|")
            for stage_name, outcomes in tr.assertions.items():
                for o in outcomes:
                    mark = "✓" if o.passed else "✗"
                    detail = o.detail.replace("|", "\\|")
                    lines.append(f"| {stage_name} | {o.name} | {mark} | {detail} |")
            lines.append("")

    return "\n".join(lines)


def render_json(result: SuiteResult) -> str:
    """Machine-readable dump. Stable shape for diffing across runs."""
    spec = result.suite

    def _kgs(s):
        return s.to_dict() if s is not None else None

    payload = {
        "suite": {
            "name": spec.name,
            "stages": [s.value for s in spec.stages],
            "topics_declared": len(spec.topics),
            "source": str(spec.source_path) if spec.source_path else None,
        },
        "all_passed": result.all_passed,
        "duration_ms": result.duration_ms,
        "total_usd": result.total_usd,
        "budget_exhausted": result.budget_exhausted,
        "error": result.error,
        "kg": {
            "before": _kgs(result.pre_stats),
            "after": _kgs(result.post_stats),
        },
        "topics": [
            {
                "topic": tr.topic,
                "run": {
                    "run_id": tr.run.run_id,
                    "stages_run": [s.value for s in tr.run.stages_run],
                    "paradigms": list(tr.run.paradigms),
                    "formulations": list(tr.run.formulations),
                    "reasoner_specs": list(tr.run.reasoner_specs),
                    "memory_per_stage": dict(tr.run.memory_per_stage),
                    "usage": dict(tr.run.usage),
                    "duration_ms": tr.run.duration_ms,
                    "failed_at": (tr.run.failed_at.value if tr.run.failed_at else None),
                    "error": tr.run.error,
                    "tool_call_log": [asdict(c) for c in tr.run.tool_call_log],
                },
                "assertions": {
                    stage: [asdict(o) for o in outs]
                    for stage, outs in tr.assertions.items()
                },
                "all_passed": tr.all_passed,
            }
            for tr in result.topic_results
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def write_report(result: SuiteResult, out_dir: Path) -> tuple[Path, Path]:
    """Write report.md + report.json. Returns the two paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"
    md_path.write_text(render_markdown(result))
    json_path.write_text(render_json(result))
    return md_path, json_path
