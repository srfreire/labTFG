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
        json.dumps(env_spec, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for key, records in trajectories.items():
        safe = key.replace("/", "_")
        (bundle / "trajectories" / f"{safe}.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    (bundle / "analyst_findings.md").write_text(analyst_findings, encoding="utf-8")
    (bundle / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if report_pdf is not None:
        (bundle / "report.pdf").write_bytes(report_pdf)
    return bundle
