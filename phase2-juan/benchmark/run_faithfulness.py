"""Faithfulness check demo/validation (Layer 3, light).

Runs a deterministic simulation, derives the ground-truth magnitudes, and scores
two reports against them: a *faithful* report (numbers match the simulation) and
an *adversarial* report with planted errors. This validates that the
faithfulness check both accepts correct reports and catches hallucinated
numbers, which is the property the memoria claims for it.

The same :func:`benchmark.faithfulness.check_report` is what would be pointed at
a live Reporter PDF/text; here we exercise it on controlled inputs so the result
is reproducible without an LLM call.

Usage (from ``phase2-juan/`` with the backend up)::

    uv run python -m benchmark.run_faithfulness
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from benchmark.baselines import GreedyForagerOracle
from benchmark.faithfulness import check_report, ground_truth_from_records
from benchmark.scenarios import build_patch_env, rollout
from shared.services import init_services, shutdown_services

REPORTS = Path(__file__).parent / "reports"


async def main() -> None:
    # The simulation itself needs no services, but we boot them so this runner
    # composes with the rest of the benchmark (and could load a Phase 1 model).
    svc = await init_services()
    try:
        recs = rollout(
            GreedyForagerOracle(seed=7),
            build_patch_env(stack=25, seed=0),
            steps=200,
            start=(0, 0),
        )
    finally:
        await shutdown_services(svc)

    mags = ground_truth_from_records(recs)
    truth = {m.key: m.value for m in mags}

    faithful = (
        f"En la simulación el agente consumió {int(truth['comida_consumida'])} "
        f"unidades de comida a lo largo de {int(truth['pasos'])} pasos, "
        f"acumulando una recompensa total de {truth['recompensa_total']:.0f}."
    )
    # Planted errors: wrong food count and wrong reward; steps left correct.
    adversarial = (
        f"En la simulación el agente consumió {int(truth['comida_consumida']) + 25} "
        f"unidades de comida a lo largo de {int(truth['pasos'])} pasos, "
        f"acumulando una recompensa total de {truth['recompensa_total'] + 40:.0f}."
    )

    rep_ok = check_report(faithful, mags)
    rep_bad = check_report(adversarial, mags)

    out = {
        "ground_truth": truth,
        "faithful_report": {
            "score": rep_ok.score,
            "results": [vars(r) for r in rep_ok.results],
        },
        "adversarial_report": {
            "score": rep_bad.score,
            "hallucinations_caught": [r.key for r in rep_bad.hallucinations],
            "results": [vars(r) for r in rep_bad.results],
        },
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "faithfulness.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    print("Ground truth:", truth)
    print(f"Faithful report   -> score {rep_ok.score:.2f}")
    print(
        f"Adversarial report -> score {rep_bad.score:.2f}, "
        f"caught: {[r.key for r in rep_bad.hallucinations]}"
    )


if __name__ == "__main__":
    asyncio.run(main())
