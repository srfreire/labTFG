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
    (env, events, agent_to_model, agent_ids_by_key)."""
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

        # 2b. Determinism check: re-simulate the full set with the same seed,
        # compare the first model's trajectory (agents share the env's resource
        # pool + RNG, so a solo re-run would not reproduce the multi-agent run).
        _, ev2, _, ids2 = await _simulate(spec, keys, models, svc.storage)
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
    (out_dir / "JUDGE_PROMPT.md").write_text(resolved, encoding="utf-8")

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
