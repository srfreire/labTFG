"""Golden-scenario benchmark runner (Phase 2, Layers 1–2).

Drives the four Phase 1 decision models and the two reference baselines through
the deterministic golden scenarios and emits a PASS/FALLA table for every
falsifiable prediction. This is pure code — no LLM — so it is fully
reproducible from the restored Phase 1 state.

Usage (from ``phase2-juan/`` with the backend services up)::

    uv run python -m benchmark.run_golden_scenarios

Outputs (written to ``benchmark/reports/``):
    - ``golden_scenarios.json``   machine-readable results
    - ``golden_scenarios.md``     human-readable report
    - ``golden_scenarios_table.tex``  LaTeX table fragment for the memoria

What it checks:
    Layer 1 — observable contract (GS-0) and engine determinism for all 6 agents.
    Layer 2 — GS-OFT-1 patch abandonment, GS-OFT-2 travel-cost comparative
              static, GS-OFT-3 diet zero-one rule, GS-RL-1 learning curve, each
              against the theory's known-truth prediction, with the baselines
              anchoring the foraging-rate floor and ceiling.
"""

from __future__ import annotations

import asyncio
import json

from simlab.model_loader import discover_models, load_model

from benchmark.baselines import GreedyForagerOracle, RandomModel
from benchmark.model_keys import AC, DIET, MVT, QL, REPORTS, SHORT, require_models
from benchmark.scenarios import (
    build_diet_env,
    build_learning_env,
    build_patch_env,
    rollout,
)
from benchmark.scoring import (
    Verdict,
    check_contract,
    check_determinism,
    reward_rate,
    score_diet_zero_one,
    score_flat,
    score_learning_curve,
    score_patch_abandonment,
    score_travel_cost,
)
from shared.services import init_services, shutdown_services

SEED = 7

# A representative perception for the GS-0 contract check (food carries x/y and
# palatability so every model — including the diet model — reads valid input).
SAMPLE_PERCEPTION = {
    "x": 1,
    "y": 1,
    "grid_width": 4,
    "grid_height": 4,
    "step": 0,
    "resources": {"food": [{"x": 2, "y": 1, "palatability": 0.9}]},
    "last_action_result": {},
}


def _prt(records) -> list[int]:
    return [int(r.state.get("patch_residence_time", 0)) for r in records]


def _diet_sets(records) -> list[list[int]]:
    return [list(r.state.get("diet_set", [])) for r in records]


def _explore(records, key_primary: str, key_alt: str) -> tuple[float, float]:
    """First/last value of an exploration-schedule key (with a fallback name)."""

    def g(s):
        return s.get(key_primary, s.get(key_alt, 0.0))

    return g(records[0].state), g(records[-1].state)


async def main() -> None:
    svc = await init_services()
    results: dict[str, list[dict]] = {
        "layer1_contract": [],
        "layer1_determinism": [],
        "layer2_golden": [],
        "anchors": [],
    }
    try:
        models = await discover_models(db=svc.db)
        require_models(models, (MVT, DIET, QL, AC))

        async def load(key: str, **kw):
            return await load_model(models[key], storage=svc.storage, **kw)

        # -- Layer 1: contract + determinism for all six agents ------------
        subjects: dict[str, object] = {}
        for key in (MVT, DIET, QL, AC):
            subjects[SHORT[key]] = await load(key, seed=SEED)
        subjects["GreedyForagerOracle (techo)"] = GreedyForagerOracle(seed=SEED)
        subjects["RandomModel (suelo)"] = RandomModel(seed=SEED)

        for name, model in subjects.items():
            v = check_contract(model, SAMPLE_PERCEPTION)
            results["layer1_contract"].append(
                {"agent": name, "passed": v.passed, "detail": v.detail}
            )

        # Determinism: two fresh runs with the same seed/config must match.
        for key in (MVT, DIET, QL, AC):
            m1 = await load(key, seed=SEED)
            m2 = await load(key, seed=SEED)
            a1 = [r.action for r in rollout(m1, build_learning_env(seed=0), steps=120)]
            a2 = [r.action for r in rollout(m2, build_learning_env(seed=0), steps=120)]
            v = check_determinism(a1, a2)
            results["layer1_determinism"].append(
                {"agent": SHORT[key], "passed": v.passed, "detail": v.detail}
            )
        for name, ctor in (
            ("GreedyForagerOracle (techo)", GreedyForagerOracle),
            ("RandomModel (suelo)", RandomModel),
        ):
            a1 = [
                r.action
                for r in rollout(ctor(seed=SEED), build_learning_env(seed=0), steps=120)
            ]
            a2 = [
                r.action
                for r in rollout(ctor(seed=SEED), build_learning_env(seed=0), steps=120)
            ]
            v = check_determinism(a1, a2)
            results["layer1_determinism"].append(
                {"agent": name, "passed": v.passed, "detail": v.detail}
            )

        golden: list[dict] = []

        # -- GS-OFT-1: patch abandonment (MVT) ----------------------------
        m = await load(MVT, seed=SEED)
        recs = rollout(m, build_patch_env(stack=25, seed=0), steps=200, start=(0, 0))
        v = score_patch_abandonment(_prt(recs))
        golden.append(
            {
                "id": "GS-OFT-1",
                "model": SHORT[MVT],
                "prediction": "Abandona el parche al decaer la tasa marginal",
                "passed": v.passed,
                "detail": v.detail,
            }
        )

        # -- GS-OFT-2: travel cost ⇒ residence (MVT) ----------------------
        common = dict(max_energy_reserves=6.0, max_patch_energy=4.0)
        m_lo = await load(MVT, seed=SEED, travel_cost_per_move=0.05, **common)
        m_hi = await load(MVT, seed=SEED, travel_cost_per_move=0.8, **common)
        prt_lo = _prt(
            rollout(m_lo, build_patch_env(stack=6, seed=0), steps=400, start=(0, 0))
        )
        prt_hi = _prt(
            rollout(m_hi, build_patch_env(stack=6, seed=0), steps=400, start=(0, 0))
        )
        v = score_travel_cost(prt_lo, prt_hi)
        golden.append(
            {
                "id": "GS-OFT-2",
                "model": SHORT[MVT],
                "prediction": "↑ coste de viaje ⇒ ↑ tiempo de residencia",
                "passed": v.passed,
                "detail": v.detail,
            }
        )

        # -- GS-OFT-3: diet zero-one rule (diet-breadth) ------------------
        m_dense = await load(DIET, seed=SEED)
        m_scarce = await load(DIET, seed=SEED)
        dense = _diet_sets(
            rollout(
                m_dense,
                build_diet_env(high_per_cell=6, n_low=6, seed=0),
                steps=160,
                start=(4, 0),
            )
        )
        scarce = _diet_sets(
            rollout(
                m_scarce,
                build_diet_env(high_per_cell=0, n_low=30, seed=0),
                steps=160,
                start=(4, 0),
            )
        )
        v = score_diet_zero_one(dense, scarce)
        golden.append(
            {
                "id": "GS-OFT-3",
                "model": SHORT[DIET],
                "prediction": "Regla 0-1: excluye la presa pobre si abunda la buena",
                "passed": v.passed,
                "detail": v.detail,
            }
        )

        # -- GS-RL-1: learning curve (RL learns, OFT flat) ----------------
        for key, scorer, label in (
            (QL, score_learning_curve, "aprende (curva ascendente)"),
            (AC, score_learning_curve, "aprende (curva ascendente)"),
            (MVT, score_flat, "control no-aprende (plano)"),
            (DIET, score_flat, "control no-aprende (plano)"),
        ):
            m = await load(key, seed=SEED)
            recs = rollout(m, build_learning_env(seed=SEED), steps=2500, start=(0, 0))
            rewards = [r.reward for r in recs]
            v: Verdict = scorer(rewards)
            extra = ""
            if key == QL:
                e0, e1 = _explore(recs, "exploration_rate", "epsilon")
                extra = f"; exploración ε {e0:.2f}→{e1:.2f}"
            elif key == AC:
                e0, e1 = _explore(recs, "beta", "beta")
                extra = f"; temperatura β {e0:.1f}→{e1:.1f}"
            golden.append(
                {
                    "id": "GS-RL-1",
                    "model": SHORT[key],
                    "prediction": label,
                    "passed": v.passed,
                    "detail": v.detail + extra,
                    "reward_rate": round(reward_rate(rewards), 3),
                }
            )

        results["layer2_golden"] = golden

        # -- Anchors: foraging-rate floor/ceiling on the learning task ----
        for name, model in (
            ("GreedyForagerOracle (techo)", GreedyForagerOracle(seed=SEED)),
            ("RandomModel (suelo)", RandomModel(seed=SEED)),
        ):
            recs = rollout(
                model, build_learning_env(seed=SEED), steps=2500, start=(0, 0)
            )
            results["anchors"].append(
                {
                    "agent": name,
                    "reward_rate": round(reward_rate([r.reward for r in recs]), 3),
                }
            )

    finally:
        await shutdown_services(svc)

    _write_reports(results)


def _mark(passed: bool) -> str:
    return "PASS" if passed else "FALLA"


def _write_reports(results: dict) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "golden_scenarios.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )

    # Markdown
    md: list[str] = ["# Golden-scenario benchmark — resultados\n"]
    md.append("## Capa 1 — contrato observable (GS-0)\n")
    md.append("| Agente | Resultado | Detalle |")
    md.append("|---|---|---|")
    for r in results["layer1_contract"]:
        md.append(f"| {r['agent']} | {_mark(r['passed'])} | {r['detail']} |")
    md.append("\n## Capa 1 — determinismo del motor\n")
    md.append("| Agente | Resultado | Detalle |")
    md.append("|---|---|---|")
    for r in results["layer1_determinism"]:
        md.append(f"| {r['agent']} | {_mark(r['passed'])} | {r['detail']} |")
    md.append("\n## Capa 2 — golden scenarios\n")
    md.append("| ID | Modelo | Predicción | Resultado | Métrica observada |")
    md.append("|---|---|---|---|---|")
    for r in results["layer2_golden"]:
        md.append(
            f"| {r['id']} | {r['model']} | {r['prediction']} | {_mark(r['passed'])} | {r['detail']} |"
        )
    md.append("\n## Anclas de forrajeo (tarea de aprendizaje)\n")
    for r in results["anchors"]:
        md.append(f"- {r['agent']}: tasa de recompensa = {r['reward_rate']}")
    (REPORTS / "golden_scenarios.md").write_text("\n".join(md) + "\n")

    # LaTeX fragment (the Layer-2 PASS/FALLA table for the memoria)
    tex: list[str] = [
        "% Auto-generado por benchmark/run_golden_scenarios.py — no editar a mano.",
        "\\begin{table}[H]",
        "\\begin{center}",
        "\\small",
        "\\begin{tabular}{|>{\\raggedright\\arraybackslash}p{1.5cm}|"
        ">{\\raggedright\\arraybackslash}p{3.0cm}|"
        ">{\\raggedright\\arraybackslash}p{4.6cm}|"
        ">{\\raggedright\\arraybackslash}p{1.4cm}|} \\hline",
        "\\textbf{ID} & \\textbf{Modelo} & \\textbf{Predicción teórica} & "
        "\\textbf{Result.} \\\\ \\hline",
    ]
    for r in results["layer2_golden"]:
        verdict = "PASS" if r["passed"] else "FALLA"
        tex.append(
            f"{r['id']} & {r['model']} & {r['prediction']} & {verdict} \\\\ \\hline"
        )
    tex += [
        "\\end{tabular}",
        "\\caption{Resultados de los \\textit{golden scenarios}: verdad teórica "
        "conocida frente al comportamiento medido en simulación (PASS/FALLA por "
        "predicción).}",
        "\\label{tab:gs-resultados}",
        "\\end{center}",
        "\\end{table}",
    ]
    (REPORTS / "golden_scenarios_table.tex").write_text("\n".join(tex) + "\n")

    print(f"Reports written to {REPORTS}/")
    print(
        f"  contract:    {sum(r['passed'] for r in results['layer1_contract'])}/{len(results['layer1_contract'])} PASS"
    )
    print(
        f"  determinism: {sum(r['passed'] for r in results['layer1_determinism'])}/{len(results['layer1_determinism'])} PASS"
    )
    print(
        f"  golden:      {sum(r['passed'] for r in results['layer2_golden'])}/{len(results['layer2_golden'])} PASS"
    )


if __name__ == "__main__":
    asyncio.run(main())
