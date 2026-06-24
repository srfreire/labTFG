"""End-to-end live-metrics run (the main validation scenario).

Drives the full Phase 2 pipeline ---Architect → simulation → Tracker →
Knowledge-Backbone write → Analyst → Reporter--- comparing two Phase 1 models
from different paradigms (Marginal Value Theorem vs tabular Q-learning), and
records the provider-dependent metrics the memoria asks for:

    - end-to-end and per-stage latency,
    - token usage and an estimated cost,
    - the environment spec the Architect produced,
    - the joinable-triple counts (Postgres row + dense + sparse vector, same
      UUID) actually persisted, counted independently in each store,
    - whether the Reporter produced the real LaTeX PDF or the standard fallback.

Makes real LLM + embedding calls (OpenRouter + Voyage). One run.

Usage (from ``phase2-juan/`` with backend up and .env present)::

    uv run python -m benchmark.run_e2e
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import random
import time
import uuid
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from simlab.analyst import Analyst
from simlab.architect import Architect
from simlab.critical_events import critical_events_to_json, detect_critical_events
from simlab.environment import Agent, Position
from simlab.knowledge import (
    ModelInfo,
    SimulationContext,
    build_writer_from_services,
)
from simlab.model_loader import discover_models, load_model
from simlab.reporter import Reporter
from simlab.spec import spec_to_environment
from simlab.tracker import Tracker

from benchmark.faithfulness import is_fallback_report
from benchmark.llm_meter import MeteredClient
from benchmark.model_keys import MVT, QL, REPORTS, require_models
from shared.services import init_services, shutdown_services

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SEED = 42
# Kept modest: the Tracker/Analyst inject events into the LLM context, so a long
# horizon overflows the 200k window. The behavioural depth lives in the
# dedicated golden-scenario benchmark; this run validates the live pipeline.
STEPS = 60

ARCHITECT_PROMPT = (
    "Diseña un entorno de rejilla 8x8 para estudiar forrajeo. Debe haber un "
    "recurso de tipo 'food' con 6 unidades que regeneran al consumirse. Las "
    "acciones disponibles son: move_up, move_down, move_left, move_right (mover "
    "una celda), eat (consume comida en la celda actual, recompensa 1) y stay "
    "(no hacer nada). Devuelve la especificación del entorno."
)


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
    """Count Qdrant points whose payload matches this experiment."""
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


async def main() -> None:
    t_start = time.perf_counter()
    svc = await init_services()
    writer = build_writer_from_services(svc)
    if writer is not None:
        svc = dataclasses.replace(svc, sim_memory_writer=writer)

    client = MeteredClient(anthropic.AsyncAnthropic(timeout=180.0))
    exp_id = str(uuid.uuid4())
    stages: dict = {}
    result: dict = {"experiment_id": exp_id, "seed": SEED, "steps": STEPS}

    try:
        models = await discover_models(db=svc.db)
        require_models(models, (MVT, QL))

        # 1. Architect → environment spec
        architect = Architect(client=client)
        with _Stage("architect", client.usage, stages):
            spec_json = await architect.run(ARCHITECT_PROMPT, max_iterations=6)
        spec = json.loads(spec_json)
        env = spec_to_environment(spec, seed=SEED)

        # Persist the experiment row so artifact registration (FK) succeeds —
        # the orchestrator does the same before running the pipeline.
        from shared.models import Experiment as DBExperiment

        async with svc.db.get_session() as session:
            session.add(
                DBExperiment(
                    id=uuid.UUID(exp_id),
                    description="benchmark e2e: MVT vs Q-learning",
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

        # 2. Add two agents from different paradigms
        rng = random.Random(SEED)
        agent_to_model: dict[str, ModelInfo] = {}
        for key in (MVT, QL):
            info = models[key]
            model = await load_model(info, storage=svc.storage, seed=SEED)
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

        # 3. Run the simulation (no LLM)
        with _Stage("simulation", client.usage, stages):
            all_events = env.run(STEPS)
        result["events"] = len(all_events)
        critical = critical_events_to_json(detect_critical_events(all_events))

        # 4. Tracker
        tracker = Tracker(client=client)
        with _Stage("tracker", client.usage, stages):
            tracker_output = await tracker.run(
                "Observa la simulación y reporta trayectorias y episodios clave.",
                all_events,
                critical_events=critical,
            )

        # 5. Persist the joinable triple, then count it in each store
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
            result["joinable_triple"] = {
                "skipped": "no sim_memory_writer (embeddings/vectors unavailable)"
            }

        # 6. Analyst
        analyst = Analyst(client=client, storage=svc.storage, db=svc.db)
        charts: list[dict] = []
        with _Stage("analyst", client.usage, stages):
            analyst_output = await analyst.run(
                "Compara los dos modelos: patrones de comportamiento, episodios "
                "críticos y relación entre acciones, recompensas y estado interno.",
                tracker_output,
                all_events,
                experiment_id=exp_id,
                charts_accumulator=charts,
                critical_events=critical,
                max_iterations=8,
            )
        result["charts_generated"] = len(charts)

        # 7. Reporter
        reporter = Reporter(client=client, storage=svc.storage, db=svc.db)
        try:
            with _Stage("reporter", client.usage, stages):
                await reporter.run(
                    "Genera un informe del experimento comparando ambos modelos.",
                    tracker_output,
                    analyst_output,
                    run_id=models[MVT].run_id or "",
                    experiment_id=exp_id,
                    charts=charts,
                )
        except Exception as exc:
            result["reporter_error"] = f"{type(exc).__name__}: {exc}"
        pdf_key = reporter.last_pdf_key
        pdf_real = None
        if pdf_key:
            pdf_bytes = await svc.storage.get(pdf_key)
            # tectonic PDFs are produced by xdvipdfmx; the fallback is Matplotlib.
            producer_fallback = b"matplotlib" in pdf_bytes.lower()
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

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "e2e_metrics.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
