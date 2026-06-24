"""Analyst attribution precision/recall (Layer 2, LLM part).

For each golden scenario this runs the real simulation, hands the LLM Analyst a
factual (deterministic) Tracker summary plus the raw events, and asks it to
attribute the behaviour to a decision-making paradigm. The attribution is scored
against the known-truth labels (table in the memoria), yielding precision/recall.

This makes real LLM calls (OpenRouter). It is a small pilot (5 scenarios), so the
numbers are reported as such, not as a statistically powered benchmark.

Usage (from ``phase2-juan/`` with backend up and .env present)::

    uv run python -m benchmark.run_analyst_pr
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from simlab.analyst import Analyst
from simlab.environment import Agent, Position
from simlab.model_loader import discover_models, load_model

from benchmark.llm_meter import MeteredClient
from benchmark.model_keys import AC, DIET, MVT, QL, REPORTS, require_models
from benchmark.scenarios import build_diet_env, build_learning_env, build_patch_env
from benchmark.scoring import detect_paradigm, pattern_recall, precision_recall
from shared.services import init_services, shutdown_services

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SEED = 7

ATTRIBUTION_PROMPT = (
    "Analiza el comportamiento del agente en esta simulación. A partir de las "
    "acciones, recompensas y variables internas observadas, identifica a qué "
    "paradigma de toma de decisiones corresponde su comportamiento y nómbralo "
    "explícitamente (por ejemplo: forrajeo óptimo —teorema del valor marginal o "
    "amplitud de dieta— frente a aprendizaje por refuerzo —Q-learning o "
    "actor-critic—). Justifica la atribución describiendo el patrón "
    "característico que la sostiene. Responde de forma concisa."
)

# (label, model key, env factory, steps, start, truth paradigm, expected pattern terms)
SCENARIOS = [
    (
        "GS-OFT-1",
        MVT,
        lambda: build_patch_env(stack=25, seed=0),
        200,
        (0, 0),
        "optimal-foraging-theory",
        ["parche", "residencia", "abandon"],
    ),
    (
        "GS-OFT-2",
        MVT,
        lambda: build_patch_env(stack=6, seed=0),
        300,
        (0, 0),
        "optimal-foraging-theory",
        ["coste", "viaje", "residencia"],
    ),
    (
        "GS-OFT-3",
        DIET,
        lambda: build_diet_env(high_per_cell=6, n_low=6, seed=0),
        160,
        (4, 0),
        "optimal-foraging-theory",
        ["dieta", "presa", "rentab"],
    ),
    (
        "GS-RL-1-QL",
        QL,
        lambda: build_learning_env(seed=SEED),
        800,
        (0, 0),
        "reinforcement-learning",
        ["aprend", "explor", "recompensa"],
    ),
    (
        "GS-RL-1-AC",
        AC,
        lambda: build_learning_env(seed=SEED),
        800,
        (0, 0),
        "reinforcement-learning",
        ["aprend", "td", "polít"],
    ),
]


def _tracker_summary(events: list, agent_id: str) -> str:
    """A deterministic, factual Tracker-style observation log (no LLM)."""
    actions = [e.action.name for e in events]
    counts = dict(Counter(actions))
    eats = sum(
        1 for e in events if e.action.name == "eat" and e.outcome.get("reward", 0) > 0
    )
    fifth = max(1, len(events) // 5)
    early = sum(e.outcome.get("reward", 0) for e in events[:fifth])
    late = sum(e.outcome.get("reward", 0) for e in events[-fifth:])
    last_state = events[-1].outcome.get("model_state", {})
    salient_keys = (
        "patch_residence_time",
        "diet_set",
        "expected_return_rate",
        "td_error",
        "exploration_rate",
        "beta",
        "delta_t",
        "energy_reserves",
        "marginal_return_rate",
    )
    salient = {k: last_state[k] for k in salient_keys if k in last_state}
    return json.dumps(
        {
            "summary": (
                f"{len(events)} pasos. Reparto de acciones: {counts}. "
                f"Comidas exitosas: {eats}. "
                f"Recompensa acumulada en el primer quinto={round(early, 2)}, "
                f"en el último quinto={round(late, 2)}."
            ),
            "trajectories": {
                agent_id: {
                    "steps": len(events),
                    "resources_consumed": eats,
                    "actions": counts,
                }
            },
            "internal_state_final": salient,
        },
        ensure_ascii=False,
    )


async def main() -> None:
    svc = await init_services()
    raw_client = anthropic.AsyncAnthropic(timeout=120.0)
    client = MeteredClient(raw_client)
    analyst = Analyst(client=client, storage=svc.storage, db=svc.db)

    rows: list[dict] = []
    try:
        models = await discover_models(db=svc.db)
        require_models(models, (MVT, DIET, QL, AC))
        for label, key, env_factory, steps, start, truth, patterns in SCENARIOS:
            model = await load_model(models[key], storage=svc.storage, seed=SEED)
            env = env_factory()
            agent_id = "subject"
            env.add_agent(
                Agent(id=agent_id, position=Position(*start), decision_model=model)
            )
            events = env.run(steps)
            tracker_output = _tracker_summary(events, agent_id)

            try:
                analysis = await analyst.run(
                    ATTRIBUTION_PROMPT,
                    tracker_output,
                    events,
                    max_iterations=8,
                    experiment_id=None,
                )
            except Exception as exc:
                analysis = f"[analyst error: {type(exc).__name__}: {exc}]"
            predicted = detect_paradigm(analysis)
            rows.append(
                {
                    "scenario": label,
                    "model": key.split("/")[1],
                    "truth": truth,
                    "predicted": predicted,
                    "correct": predicted == truth,
                    "pattern_recall": round(pattern_recall(analysis, patterns), 2),
                    "analysis_excerpt": analysis[:280],
                }
            )
            print(
                f"{label}: truth={truth} predicted={predicted} ok={predicted == truth}"
            )
    finally:
        await shutdown_services(svc)

    metrics = precision_recall(
        [r["predicted"] for r in rows], [r["truth"] for r in rows]
    )
    metrics["mean_pattern_recall"] = round(
        sum(r["pattern_recall"] for r in rows) / len(rows), 3
    )
    out = {"metrics": metrics, "rows": rows, "usage": client.usage.as_dict()}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "analyst_pr.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False)
    )

    print("\nMetrics:", metrics)
    print("Usage:", client.usage.as_dict())


if __name__ == "__main__":
    asyncio.run(main())
