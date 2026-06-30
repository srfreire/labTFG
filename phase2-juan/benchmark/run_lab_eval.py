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
from benchmark.model_keys import (
    CASO1,
    CASO1_SHORT,
    CASO2,
    CASO2_SHORT,
    REPORTS,
    require_models,
)
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
    "caso2": {
        "keys": CASO2,
        "short": CASO2_SHORT,
        "architect_prompt": (
            "Diseña un entorno de rejilla 10x10 para estudiar la regulación "
            "homeostática y la defensa de un punto de equilibrio (setpoint) "
            "mediante la ingesta. Debe haber recursos de tipo 'food' (al menos 8 "
            "unidades que regeneran al consumirse), cada uno con atributos de "
            "valor observables, en particular 'palatability' y 'energy_content' "
            "(cuánta energía aporta al consumirse, para reducir el déficit "
            "interno del agente). Las acciones disponibles son: move_up, "
            "move_down, move_left, move_right (mover una celda), eat (consume "
            "comida en la celda actual, recompensa según su valor nutricional) y "
            "stay. Devuelve la especificación del entorno."
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
                {
                    "type": r["type"],
                    "count": r.get("count"),
                    "regenerate": r.get("regenerate"),
                }
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
                # 6-model runs (CASO1) occasionally need >8 agentic iterations to
                # finish the observation; the default cap aborts the whole run.
                max_iterations=12,
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
                # Only a non-trivial consistency: 0==0==0==0 is vacuous, so flag
                # it explicitly rather than letting `consistent: true` mask an
                # empty write.
                "consistent": (pg == written == dense == sparse),
                "all_zero": written == 0,
                "skipped_reason": wr.skipped_reason,
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
                # 6-model comparisons (CASO1) occasionally exceed 8 agentic
                # iterations and abort the whole run; 10 absorbs that variance
                # without letting the loop wander.
                max_iterations=10,
            )
        result["charts_generated"] = len(charts)

        # 6. Reporter
        # Pin the real spec into the report so the LLM cannot invent the grid
        # size / action set / resource count (judge CASO1 flagged "5x5", "5
        # acciones", "5 recursos" — all hallucinated because env_facts was None).
        grid = spec.get("grid") or {}
        # Authoritative per-model + total consumption, so the Reporter quotes the
        # real foraging-success count instead of summing by eye (judge CASO2:
        # "9 eventos de forrajeo" when the trajectories sum to 7). tracker.run()
        # returns a JSON *string*; parse it into its own var so we don't clobber
        # the per-model `trajectories` dict the judge bundle is built from. The
        # Tracker keys trajectories by formulation (the part after "/").
        try:
            tracker_trajs = json.loads(tracker_output).get("trajectories", {})
        except (json.JSONDecodeError, TypeError, AttributeError):
            tracker_trajs = {}
        consumption = {}
        actions_by_model = {}
        for k in keys:
            traj = tracker_trajs.get(k) or tracker_trajs.get(k.split("/")[-1]) or {}
            consumed = traj.get("resources_consumed")
            if consumed is not None:
                consumption[cfg["short"].get(k, k)] = consumed
            acts = traj.get("actions")
            if isinstance(acts, dict) and acts:
                actions_by_model[cfg["short"].get(k, k)] = acts
        env_facts = {
            "grid_w": grid.get("width"),
            "grid_h": grid.get("height"),
            "resources": [
                {"type": r["type"], "count": r.get("count")}
                for r in spec.get("resources", [])
            ],
            "steps": STEPS,
            "actions": [a["name"] for a in spec.get("actions", [])],
            "models": [cfg["short"].get(k, k) for k in keys],
            "consumption": consumption,
            "total_consumed": sum(consumption.values()) if consumption else None,
            "actions_by_model": actions_by_model,
            "seed": SEED,
        }
        # Sonnet, not the Haiku default: the eval measures report FIDELITY, and
        # Haiku reliably leaks chatty meta-monologues ("¿Qué puedo hacer?",
        # "Según tus instrucciones..."), stray \section commands and deliberation
        # into the LaTeX body — confounding the judge's fidelity read with output
        # hygiene. This mirrors the production quality="detailed" path.
        reporter = Reporter(
            client=client,
            storage=svc.storage,
            db=svc.db,
            model="anthropic/claude-sonnet-4-5",
        )
        try:
            with _Stage("reporter", client.usage, stages):
                await reporter.run(
                    "Genera un informe del experimento comparando los modelos.",
                    tracker_output,
                    analyst_output,
                    run_id=models[keys[0]].run_id or "",
                    experiment_id=exp_id,
                    charts=charts,
                    env_facts=env_facts,
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
        tracker_output=tracker_output,
        analyst_findings=analyst_output or "(sin salida del Analyst)",
        report_pdf=report_pdf,
        metrics=result,
    )
    prompt_template = (Path(__file__).resolve().parent / "JUDGE_PROMPT.md").read_text()
    resolved = prompt_template.replace("{BUNDLE_DIR}", str(bundle.resolve()))
    (out_dir / "JUDGE_PROMPT.md").write_text(resolved, encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n" + "=" * 70)
    print("Run del lab completa. Para el juicio, ejecuta Codex así:\n")
    print(f"  cd {bundle.resolve().parent}")
    print('  codex exec "$(cat JUDGE_PROMPT.md)"')
    print(f"\nCodex debe escribir el veredicto en: {out_dir.resolve()}/llm-judge.md")
    print("=" * 70)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="caso1")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args().case))
