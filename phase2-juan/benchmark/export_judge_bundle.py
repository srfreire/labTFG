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

from simlab.tools import _make_serializable


def export_judge_bundle(
    out_dir: Path,
    *,
    env_spec: dict,
    trajectories: dict[str, list[dict]],
    tracker_output: str,
    analyst_findings: str,
    report_pdf: bytes | None,
    metrics: dict,
) -> Path:
    bundle = out_dir / "judge-bundle"
    (bundle / "trajectories").mkdir(parents=True, exist_ok=True)

    # The Tracker's raw observation — the judge needs it to assess observation
    # fidelity (rubric criterion 2) directly, not just via the joinable triple.
    (bundle / "tracker_output.json").write_text(tracker_output, encoding="utf-8")

    (bundle / "env_spec.json").write_text(
        json.dumps(env_spec, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for key, records in trajectories.items():
        safe = key.replace("/", "_")
        # Per-step model_state can carry non-JSON keys (e.g. a Q-table keyed by
        # (state, action) tuples). Normalize before dumping — same helper the
        # simulation tools use, so the bundle matches what the agents observed.
        (bundle / "trajectories" / f"{safe}.json").write_text(
            json.dumps(_make_serializable(records), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    (bundle / "analyst_findings.md").write_text(analyst_findings, encoding="utf-8")
    (bundle / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if report_pdf is not None:
        (bundle / "report.pdf").write_bytes(report_pdf)
    return bundle
