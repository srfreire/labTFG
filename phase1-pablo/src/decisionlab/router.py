"""Pipeline orchestration and human feedback routing."""

from __future__ import annotations

import json
import logging
import re
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import agrex
from rich.console import Console

from decisionlab.domain.models import RerunRequest
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    create_retrieve_knowledge,
)
from decisionlab.parsing import FORMULATION_HEADER_RE
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from decisionlab.agents.memory_agent import MemoryAgent
    from decisionlab.domain.ports import WebSearchPort

logger = logging.getLogger(__name__)

# Type alias for the emit callback (async)
EmitFn = Callable[[dict], Awaitable[None]]

# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class Stage(StrEnum):
    RESEARCH = "research"
    MEMORY_RESEARCH = "memory_research"
    REVIEW_RESEARCH = "review_research"
    FORMALIZE = "formalize"
    MEMORY_FORMALIZE = "memory_formalize"
    REVIEW_FORMALIZE = "review_formalize"
    GET_ENV_SPEC = "get_env_spec"
    REASON = "reason"
    MEMORY_REASON = "memory_reason"
    REVIEW_REASON = "review_reason"
    BUILD = "build"
    MEMORY_BUILD = "memory_build"
    REVIEW_BUILD = "review_build"
    DONE = "done"


# Mapping work stage → Memory Agent stage name (used in MemoryAgent.run()).
_MEMORY_AGENT_STAGE_NAMES = {
    Stage.RESEARCH: "researcher",
    Stage.FORMALIZE: "formalizer",
    Stage.REASON: "reasoner",
    Stage.BUILD: "builder",
}

# Mapping work stage → its dedicated MEMORY_X stage. Each work handler
# advances to MEMORY_X when memory infra is available; the loop then runs
# the matching _memory_<stage> handler which awaits the Memory Agent
# synchronously before yielding to the REVIEW_X stage.
_MEMORY_STAGE_OF = {
    Stage.RESEARCH: Stage.MEMORY_RESEARCH,
    Stage.FORMALIZE: Stage.MEMORY_FORMALIZE,
    Stage.REASON: Stage.MEMORY_REASON,
    Stage.BUILD: Stage.MEMORY_BUILD,
}

# Mapping MEMORY_X → the work stage it follows (used by _memory_<stage>
# handlers to look up the right output text and agent name).
_WORK_STAGE_OF_MEMORY = {v: k for k, v in _MEMORY_STAGE_OF.items()}

# Mapping MEMORY_X → the REVIEW_X it transitions into when finished.
_REVIEW_AFTER_MEMORY = {
    Stage.MEMORY_RESEARCH: Stage.REVIEW_RESEARCH,
    Stage.MEMORY_FORMALIZE: Stage.REVIEW_FORMALIZE,
    Stage.MEMORY_REASON: Stage.REVIEW_REASON,
    Stage.MEMORY_BUILD: Stage.REVIEW_BUILD,
}

# Work stages that emit a `tracer.stage(...)` timeline event (memory and
# review sub-stages are intentionally excluded — they'd be timeline noise).
_TIMELINE_WORK_STAGES = {
    Stage.RESEARCH,
    Stage.FORMALIZE,
    Stage.REASON,
    Stage.BUILD,
}

# Review stages that emit a yellow `tracer.marker(...)` at the prompt.
_REVIEW_STAGES = {
    Stage.REVIEW_RESEARCH,
    Stage.REVIEW_FORMALIZE,
    Stage.REVIEW_REASON,
    Stage.REVIEW_BUILD,
}


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    stage: Stage
    problem: str
    reports_dir: Path
    run_id: str = ""

    # Filled progressively
    approved_paradigms: list[str] = field(default_factory=list)
    selected_formulations: dict[str, list[str]] = field(default_factory=dict)
    env_spec_path: Path | None = None
    approved_specs: dict[str, list[str]] = field(default_factory=dict)
    build_results: dict[str, str] = field(default_factory=dict)
    pending_reruns: list[RerunRequest] = field(default_factory=list)

    # -- S3 prefix helpers ---------------------------------------------------

    @property
    def research_prefix(self) -> str:
        return f"research/{self.run_id}"

    @property
    def models_prefix(self) -> str:
        return f"models/{self.run_id}"

    # -- persistence ---------------------------------------------------------

    async def save(self) -> None:
        """Save state to S3 at research/{run_id}/pipeline_state.json."""
        import shared

        data = {
            "stage": self.stage.value,
            "problem": self.problem,
            "run_id": self.run_id,
            "approved_paradigms": self.approved_paradigms,
            "selected_formulations": self.selected_formulations,
            "env_spec_path": str(self.env_spec_path) if self.env_spec_path else None,
            "approved_specs": self.approved_specs,
            "build_results": self.build_results,
            "pending_reruns": [
                {"target": r.target, "paradigm": r.paradigm, "feedback": r.feedback}
                for r in self.pending_reruns
            ],
        }
        key = f"research/{self.run_id}/pipeline_state.json"
        await shared.storage.put_text(key, json.dumps(data, indent=2))
        logger.debug("PipelineState saved to s3://%s", key)

    @classmethod
    async def load(cls, run_id: str) -> PipelineState:
        """Load state from S3 and verify referenced artifacts still exist.

        Raises ``FileNotFoundError`` when the state file itself is missing,
        or ``RuntimeError`` when the state references artifacts (formulation
        markdown, reasoner specs, builder models) that are not on S3 — which
        usually means a previous run crashed mid-stage and left the state
        ahead of the actual outputs.
        """
        import shared

        key = f"research/{run_id}/pipeline_state.json"
        try:
            raw = await shared.storage.get_text(key)
            data = json.loads(raw)
        except Exception:
            raise FileNotFoundError(f"Pipeline state not found at s3://{key}") from None

        env_path = data.get("env_spec_path")
        state = cls(
            stage=Stage(data["stage"]),
            problem=data["problem"],
            reports_dir=Path(data.get("reports_dir", ".")),
            run_id=data.get("run_id", run_id),
            approved_paradigms=data.get("approved_paradigms", []),
            selected_formulations=data.get("selected_formulations", {}),
            env_spec_path=Path(env_path) if env_path else None,
            approved_specs=data.get("approved_specs", {}),
            build_results=data.get("build_results", {}),
            pending_reruns=[
                RerunRequest(
                    target=r["target"], paradigm=r["paradigm"], feedback=r["feedback"]
                )
                for r in data.get("pending_reruns", [])
            ],
        )

        missing = await state._missing_artifacts()
        if missing:
            preview = ", ".join(missing[:5])
            extra = f" (and {len(missing) - 5} more)" if len(missing) > 5 else ""
            raise RuntimeError(
                f"Cannot resume run {run_id}: state references {len(missing)} "
                f"missing artifact(s) on S3: {preview}{extra}. "
                f"The previous run likely crashed mid-stage. Roll the state "
                f"back to an earlier stage or start a fresh run."
            )

        return state

    async def _missing_artifacts(self) -> list[str]:
        """Return S3 keys this state references that don't exist on the bucket.

        Walks the artifacts implied by each filled-in state field. Empty fields
        are skipped (a state in early RESEARCH has nothing to validate beyond
        itself). Returns an empty list when state is coherent.
        """
        import shared

        candidates: list[str] = []
        for slug in self.approved_paradigms:
            candidates.append(f"{self.research_prefix}/formulations/{slug}.md")
        for paradigm, fids in self.selected_formulations.items():
            for fid in fids:
                candidates.append(
                    f"{self.models_prefix}/reasoner/{paradigm}/{fid}.json"
                )
        for paradigm, fids in self.approved_specs.items():
            for fid in fids:
                candidates.append(
                    f"{self.models_prefix}/builder/{paradigm}/{fid}_model.py"
                )

        missing: list[str] = []
        for key in candidates:
            try:
                if not await shared.storage.exists(key):
                    missing.append(key)
            except Exception:
                # Storage unreachable → don't pretend the artifact is missing;
                # let the caller surface the connection error elsewhere.
                logger.warning(
                    "S3 reachability check failed for %s", key, exc_info=True
                )
                return []
        return missing


async def _convert_formulations_to_slugs(
    state: PipelineState,
    raw_selected: dict[str, list[int]],
) -> dict[str, list[str]]:
    """Convert ``{slug: [int]}`` from feedback to ``{slug: [formulation_slug]}``."""
    import shared

    converted: dict[str, list[str]] = {}
    for slug, kept_numbers in raw_selected.items():
        if not kept_numbers:
            converted[slug] = []
            continue
        key = f"research/{state.run_id}/formulations/{slug}.md"
        try:
            text = await shared.storage.get_text(key)
        except Exception:
            logger.warning("Formulation file not found for '%s'; skipping", slug)
            converted[slug] = []
            continue
        num_to_name = {
            int(m.group(1)): m.group(2).strip()
            for m in FORMULATION_HEADER_RE.finditer(text)
        }
        slugs: list[str] = []
        for num in kept_numbers:
            name = num_to_name.get(num)
            if name is None:
                logger.warning("Formulation %d not found in %s.md", num, slug)
                continue
            slugs.append(slugify(name))
        converted[slug] = slugs
    return converted


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class Router:
    def __init__(
        self,
        client: AsyncAnthropic,
        state: PipelineState,
        search: WebSearchPort,
        project_root: Path,
        emit: EmitFn | None = None,
        stop_after: Stage | None = None,
    ):
        self.client = client
        self.state = state
        self.search = search
        self.project_root = project_root
        self.console = Console()
        self.emit = emit  # None → CLI mode; set → web mode
        self._web_mode = emit is not None
        self.memory_agent: MemoryAgent | None = self._init_memory_agent()
        # Per-stage output cache populated by work-stage handlers when they
        # have the text in-memory (e.g. Researcher's return value). Falls back
        # to S3 reads in `_collect_stage_output` for stages whose agents don't
        # yet return text directly (formalize/reason/build).
        self._stage_outputs: dict[Stage, str] = {}
        # When set, the loop terminates after the corresponding REVIEW_X stage
        # completes. Must be one of the work stages (research/formalize/reason
        # /build); validated by the caller. The trailing review is preserved
        # so the user can still curate the partial-run output before it's
        # committed to the KG.
        if stop_after is not None and stop_after not in _MEMORY_STAGE_OF:
            raise ValueError(f"stop_after must be a work stage, got {stop_after!r}")
        self._stop_after: Stage | None = stop_after
        self._stop_after_review: Stage | None = (
            _REVIEW_AFTER_MEMORY[_MEMORY_STAGE_OF[stop_after]]
            if stop_after is not None
            else None
        )
        self._tracer: agrex.Tracer | None = None
        self._trace_local_path: Path | None = None

    def _knowledge_tool_kwargs(self, stage: str) -> dict:
        """Return keyword args for knowledge tool injection into an agent.

        Returns ``{"knowledge_tool_schema": ..., "knowledge_tool_handler": ...}``
        when knowledge infrastructure is available, otherwise an empty dict
        (agent runs without the tool — graceful degradation).
        """
        try:
            import shared

            kg = getattr(shared, "kg", None)
            vectors = getattr(shared, "vectors", None)
            embeddings = getattr(shared, "embeddings", None)

            if kg is None and vectors is None and embeddings is None:
                return {}

            handler = create_retrieve_knowledge(
                kg=kg,
                vector_store=vectors,
                embedding_service=embeddings,
                search_adapter=self.search,
                client=self.client,
                run_id=self.state.run_id,
                stage=stage,
            )
            return {
                "knowledge_tool_schema": RETRIEVE_KNOWLEDGE_SCHEMA,
                "knowledge_tool_handler": handler,
            }
        except Exception:
            logger.debug("Could not create retrieve_knowledge for stage=%s", stage)
            return {}

    def _init_memory_agent(self) -> MemoryAgent | None:
        """Create a MemoryAgent if knowledge infrastructure is available."""
        try:
            import shared

            if shared.db is None:
                return None
            from decisionlab.agents.memory_agent import MemoryAgent

            return MemoryAgent(
                client=self.client,
                kg=getattr(shared, "kg", None),
                vector_store=getattr(shared, "vectors", None),
                embedding_service=getattr(shared, "embeddings", None),
                db=shared.db,
            )
        except Exception:
            logger.debug("Knowledge infrastructure unavailable — Memory Agent disabled")
            return None

    async def _send_event(self, msg: dict) -> None:
        """Forward an event to the frontend (no-op in CLI mode)."""
        if self.emit is not None:
            await self.emit(msg)

    def _init_trace(self, run_id: str) -> None:
        """Open a per-run trace file and create an agrex.Tracer streaming to it.

        The local file is uploaded to s3://research/{run_id}/trace.jsonl in
        _finalize_trace. Idempotent: a second call replaces any prior tracer.
        """
        if self._tracer is not None:
            try:
                self._tracer.close()
            except Exception:
                logger.warning(
                    "Prior tracer close failed during _init_trace", exc_info=True
                )
        if self._trace_local_path is not None:
            try:
                self._trace_local_path.unlink(missing_ok=True)
            except Exception:
                logger.warning(
                    "Prior trace local cleanup failed: %s",
                    self._trace_local_path,
                    exc_info=True,
                )

        fd, path = tempfile.mkstemp(prefix=f"agrex-{run_id}-", suffix=".jsonl")
        self._trace_local_path = Path(path)
        # File handle ownership transfers to the Tracer (closed by tracer.close()).
        file_handle = open(fd, "w", encoding="utf-8")  # noqa: SIM115
        self._tracer = agrex.create_tracer(out=file_handle)
        logger.debug("Trace recording started: %s", self._trace_local_path)

    async def _finalize_trace(self, run_id: str) -> None:
        """Close the tracer and upload the trace file to S3.

        Safe to call multiple times. Failures are logged but never raised
        so a trace upload failure cannot abort run finalization.
        """
        if self._tracer is None:
            return
        try:
            self._tracer.close()
        except Exception:
            logger.warning("Tracer close failed", exc_info=True)

        local_path = self._trace_local_path
        try:
            if local_path is not None and local_path.exists():
                content = local_path.read_text(encoding="utf-8")
                import shared

                if shared.storage is not None:
                    key = f"research/{run_id}/trace.jsonl"
                    await shared.storage.put_text(key, content)
                    logger.debug(
                        "Trace uploaded to s3://%s (%d bytes)", key, len(content)
                    )
        except Exception:
            logger.warning("Trace S3 upload failed for run %s", run_id, exc_info=True)
        finally:
            if local_path is not None:
                try:
                    local_path.unlink(missing_ok=True)
                except Exception:
                    logger.warning(
                        "Trace local cleanup failed: %s", local_path, exc_info=True
                    )
            self._tracer = None
            self._trace_local_path = None

    async def _emit_agents(self) -> None:
        """Emit the list of pipeline agents so the frontend can build its panel."""
        agents: list[dict] = [
            {"name": "researcher", "color": "#4a9eff"},
            {"name": "formalizer", "color": "#9b59b6"},
            {"name": "reasoner", "color": "#ff6b4a"},
            {"name": "builder", "color": "#fbbf24"},
        ]
        if self.memory_agent is not None:
            agents.append({"name": "memory_agent", "color": "#22d3ee"})
        await self._send_event({"type": "agents", "agents": agents})

    # -- DB helpers -----------------------------------------------------------

    async def _update_run(self, **values) -> None:
        """Update the Run row in Postgres with the given column values."""
        from sqlalchemy import update

        import shared
        from shared.models import Run

        async with shared.db.get_session() as session:
            await session.execute(
                update(Run)
                .where(Run.id == uuid.UUID(self.state.run_id))
                .values(**values)
            )
            await session.commit()

    # -- memory agent ---------------------------------------------------------

    def _next_after_work(self, work_stage: Stage) -> Stage:
        """Stage to transition to after a work handler succeeds. Goes through
        the MEMORY_X interstitial when memory infra is up; otherwise straight
        to REVIEW_X (memory tick is a no-op in degraded mode)."""
        memory_stage = _MEMORY_STAGE_OF[work_stage]
        if self.memory_agent is None:
            return _REVIEW_AFTER_MEMORY[memory_stage]
        return memory_stage

    async def _run_memory_stage(self, memory_stage: Stage) -> None:
        """Body of every _memory_<stage> handler. Awaits the Memory Agent
        synchronously, persists the per-stage result (or error) on the run
        row, then advances to the matching REVIEW_X. Failures never block
        the pipeline — they're recorded for post-hoc inspection via the
        runs.memory_results JSONB column."""
        work_stage = _WORK_STAGE_OF_MEMORY[memory_stage]
        review_stage = _REVIEW_AFTER_MEMORY[memory_stage]
        agent_name = _MEMORY_AGENT_STAGE_NAMES[work_stage]

        if self.memory_agent is None:
            self.state.stage = review_stage
            return

        payload: dict
        try:
            output = await self._collect_stage_output(work_stage)
            result = await self.memory_agent.run(
                agent_name, output, self.state.run_id, emit=self.emit
            )
            logger.info("Memory Agent [%s] completed: %s", agent_name, result)
            payload = {
                "status": "failed" if result.failed else "ok",
                "nodes_created": result.nodes_created,
                "nodes_merged": result.nodes_merged,
                "relations_created": result.relations_created,
                "facts_stored": result.facts_stored,
                "duplicates_skipped": result.duplicates_skipped,
                "conflicts_resolved": result.conflicts_resolved,
                "duration_ms": result.duration_ms,
            }
            if result.error:
                payload["error"] = result.error
        except Exception as exc:
            logger.exception(
                "Memory Agent failed for stage=%s — continuing pipeline",
                agent_name,
            )
            payload = {"status": "failed", "error": str(exc)}

        await self._record_memory_result(agent_name, payload)
        self.state.stage = review_stage

    async def _record_memory_result(self, agent_name: str, payload: dict) -> None:
        """Merge a per-stage Memory Agent result into runs.memory_results.
        Read-modify-write is fine here: the Router is the sole writer for any
        given run, so there's no concurrent-update race to worry about."""
        import shared
        from shared.models import Run

        try:
            async with shared.db.get_session() as session:
                run = await session.get(Run, uuid.UUID(self.state.run_id))
                if run is None:
                    return
                merged = dict(run.memory_results or {})
                merged[agent_name] = payload
                run.memory_results = merged
                await session.commit()
        except Exception:
            logger.exception(
                "Failed to persist memory_results for stage=%s — continuing",
                agent_name,
            )

    async def _memory_research(self) -> None:
        await self._run_memory_stage(Stage.MEMORY_RESEARCH)

    async def _memory_formalize(self) -> None:
        await self._run_memory_stage(Stage.MEMORY_FORMALIZE)

    async def _memory_reason(self) -> None:
        await self._run_memory_stage(Stage.MEMORY_REASON)

    async def _memory_build(self) -> None:
        await self._run_memory_stage(Stage.MEMORY_BUILD)

    async def _run_consolidation(self) -> None:
        """Run post-run consolidation. Never blocks pipeline."""
        try:
            import shared
            from decisionlab.knowledge.consolidation import consolidate

            if shared.db is None or shared.embeddings is None or shared.vectors is None:
                return

            async with shared.db.get_session() as session:
                result = await consolidate(
                    db_session=session,
                    embedding_service=shared.embeddings,
                    vector_store=shared.vectors,
                    client=self.client,
                    run_id=self.state.run_id,
                    kg=getattr(shared, "kg", None),
                )
            logger.info("Consolidation completed: %s", result)
        except Exception:
            logger.exception("Consolidation failed — continuing pipeline")

    async def _collect_stage_output(self, stage: Stage) -> str:
        """Return the stage's output text. Prefers the in-memory cache populated
        by the work handler; falls back to reading from S3 (used for resumed
        runs and for stages whose handlers don't cache directly yet)."""
        cached = self._stage_outputs.get(stage)
        if cached is not None:
            return cached

        import shared

        prefix = self.state.research_prefix
        models = self.state.models_prefix

        if stage == Stage.RESEARCH:
            key = f"{prefix}/report.md"
            try:
                text = await shared.storage.get_text(key)
            except Exception:
                logger.warning("Could not read research report from %s", key)
                return ""
            self._stage_outputs[stage] = text
            return text

        if stage == Stage.FORMALIZE:
            parts: list[str] = []
            for slug in self.state.approved_paradigms:
                key = f"{prefix}/formulations/{slug}.md"
                try:
                    parts.append(await shared.storage.get_text(key))
                except Exception:
                    logger.warning("Could not read formulation %s", key)
            text = "\n\n".join(parts)
            self._stage_outputs[stage] = text
            return text

        if stage == Stage.REASON:
            parts = []
            for paradigm, fids in self.state.selected_formulations.items():
                for fid in fids:
                    key = f"{models}/reasoner/{paradigm}/{fid}.json"
                    try:
                        parts.append(await shared.storage.get_text(key))
                    except Exception:
                        logger.warning("Could not read reasoner spec %s", key)
            text = "\n\n".join(parts)
            self._stage_outputs[stage] = text
            return text

        if stage == Stage.BUILD:
            parts = []
            for paradigm, fids in self.state.approved_specs.items():
                for fid in fids:
                    model_key = f"{models}/builder/{paradigm}/{fid}_model.py"
                    try:
                        parts.append(await shared.storage.get_text(model_key))
                    except Exception:
                        logger.warning("Could not read builder model %s", model_key)
            if self.state.build_results:
                parts.append(str(self.state.build_results))
            text = "\n\n".join(parts)
            self._stage_outputs[stage] = text
            return text

        return ""

    # -- main loop -----------------------------------------------------------

    async def run(self) -> None:
        handlers = {
            Stage.RESEARCH: self._do_research,
            Stage.MEMORY_RESEARCH: self._memory_research,
            Stage.REVIEW_RESEARCH: self._review_research,
            Stage.FORMALIZE: self._do_formalize,
            Stage.MEMORY_FORMALIZE: self._memory_formalize,
            Stage.REVIEW_FORMALIZE: self._review_formalize,
            Stage.GET_ENV_SPEC: self._get_env_spec,
            Stage.REASON: self._do_reason,
            Stage.MEMORY_REASON: self._memory_reason,
            Stage.REVIEW_REASON: self._review_reason,
            Stage.BUILD: self._do_build,
            Stage.MEMORY_BUILD: self._memory_build,
            Stage.REVIEW_BUILD: self._review_build,
        }

        self._init_trace(self.state.run_id)
        try:
            await self._run_loop(handlers)
        finally:
            await self._finalize_trace(self.state.run_id)

    async def _run_loop(self, handlers: dict) -> None:
        # Emit agent list so the frontend knows which agents are available
        await self._emit_agents()

        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]

            if current_stage in _TIMELINE_WORK_STAGES:
                self._tracer.stage(current_stage.value)
                await self._send_event(self._tracer.events()[-1])
            elif current_stage in _REVIEW_STAGES:
                # The review stage's value is already "review_<work>" (e.g. "review_research"),
                # which is exactly the marker kind we want.
                self._tracer.marker(current_stage.value, color="#fbbf24")
                await self._send_event(self._tracer.events()[-1])

            await handler()

            # `--until X` enforcement: when the user just finished reviewing the
            # stop_after stage, terminate cleanly. Consolidation + finalization
            # still run via the block below.
            if (
                self._stop_after_review is not None
                and current_stage == self._stop_after_review
            ):
                self.state.stage = Stage.DONE

            await self.state.save()
            await self._update_run(status=self.state.stage.value)

        # Finalize run: consolidation + s3_report_key. final_stage is set
        # only on partial runs so `final_stage IS NULL` keeps meaning
        # "ran the full pipeline".
        if self.state.stage == Stage.DONE:
            if self.memory_agent is not None:
                await self._run_consolidation()
            updates: dict = {
                "s3_report_key": f"{self.state.research_prefix}/report.md",
            }
            if self._stop_after is not None:
                updates["final_stage"] = self._stop_after.value
            await self._update_run(**updates)

    # -- stage handlers ------------------------------------------------------

    async def _do_research(self) -> None:
        from decisionlab.agents.researcher import Researcher

        self.console.print("[bold]Running Researcher...[/bold]")
        self._tracer.agent("researcher", "Researcher")
        await self._send_event(self._tracer.events()[-1])
        try:
            r = Researcher(
                client=self.client,
                search=self.search,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("researcher"),
            )
            report = await r.run(self.state.problem)
        except Exception as exc:
            self.console.print(f"[bold red]Researcher failed: {exc}[/bold red]")
            logger.exception("Researcher failed")
            self._tracer.error("researcher", error=exc)
            await self._send_event(self._tracer.events()[-1])
            return  # stay at current stage
        # Cache the in-memory text so the Memory Agent doesn't round-trip S3.
        self._stage_outputs[Stage.RESEARCH] = report.summary
        self._tracer.done("researcher")
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.RESEARCH)

    async def _review_research(self) -> None:
        from decisionlab.agents.deep_researcher import DeepResearcher

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_research

                assert self.emit is not None
                approved, additional = await review_research(
                    self.state.reports_dir,
                    self.emit,
                )
            else:
                from decisionlab.feedback import review_research

                approved, additional = await review_research(
                    self.state.reports_dir,
                )
            if additional:
                self.console.print(
                    f"[bold]Running DeepResearcher for '{additional}'...[/bold]"
                )
                try:
                    dr = DeepResearcher(
                        client=self.client,
                        search=self.search,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("deep_researcher"),
                    )
                    await dr.run(additional)
                except Exception as exc:
                    self.console.print(
                        f"[bold red]DeepResearcher failed for '{additional}': {exc}[/bold red]"
                    )
                    logger.exception("DeepResearcher failed for %s", additional)
                # Loop back to let user review again
                continue
            # No more additions — store approved slugs
            self.state.approved_paradigms = approved
            await self.state.save()
            break
        self.state.stage = Stage.FORMALIZE

    async def _do_formalize(self) -> None:
        from decisionlab.agents.formalizer import Formalizer

        self.console.print("[bold]Running Formalizer...[/bold]")
        self._tracer.agent("formalizer", "Formalizer", parent="researcher")
        await self._send_event(self._tracer.events()[-1])
        try:
            f = Formalizer(
                client=self.client,
                research_prefix=self.state.research_prefix,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("formalizer"),
            )
            await f.run(self.state.approved_paradigms)
        except Exception as exc:
            self.console.print(f"[bold red]Formalizer failed: {exc}[/bold red]")
            logger.exception("Formalizer failed")
            self._tracer.error("formalizer", error=exc)
            await self._send_event(self._tracer.events()[-1])
            return
        self._tracer.done("formalizer")
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.FORMALIZE)

    async def _review_formalize(self) -> None:
        if self._web_mode:
            from decisionlab.web_feedback import review_formalize

            assert self.emit is not None
            selected = await review_formalize(
                self.state.reports_dir,
                self.state.approved_paradigms,
                self.emit,
                run_id=self.state.run_id,
            )
        else:
            from decisionlab.feedback import review_formalize

            selected = await review_formalize(
                self.state.reports_dir,
                self.state.approved_paradigms,
                run_id=self.state.run_id,
            )
        self.state.selected_formulations = await _convert_formulations_to_slugs(
            self.state,
            selected,
        )
        await self.state.save()
        from decisionlab.tools.reports import generate_tree_map

        await generate_tree_map(self.state)
        self.state.stage = Stage.GET_ENV_SPEC

    async def _get_env_spec(self) -> None:
        import shared

        try:
            if self._web_mode:
                from decisionlab.web_feedback import get_env_spec

                assert self.emit is not None
                src_path = await get_env_spec(self.emit)
            else:
                from decisionlab.feedback import get_env_spec

                src_path = await get_env_spec()
            # Upload env_spec to S3
            env_spec_data = src_path.read_text()
            s3_key = f"research/{self.state.run_id}/env_spec.json"
            await shared.storage.put_text(s3_key, env_spec_data)
            self.state.env_spec_path = Path(s3_key)  # transitional
        except Exception as exc:
            self.console.print(f"[bold red]env_spec setup failed: {exc}[/bold red]")
            logger.exception("env_spec setup failed")
            return
        self.state.stage = Stage.REASON

    async def _do_reason(self) -> None:
        from decisionlab.agents.reasoner import Reasoner

        selected = self.state.selected_formulations
        n_formulations = sum(len(v) for v in selected.values())
        self.console.print(
            f"[bold]Running Reasoner for {n_formulations} formulation(s) "
            f"across {len(selected)} paradigm(s)...[/bold]"
        )
        self._tracer.agent("reasoner", "Reasoner", parent="formalizer")
        await self._send_event(self._tracer.events()[-1])
        try:
            r = Reasoner(
                client=self.client,
                research_prefix=self.state.research_prefix,
                models_prefix=self.state.models_prefix,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("reasoner"),
            )
            await r.run(selected)
            await self._validate_reasoner_files(selected)
        except Exception as exc:
            self.console.print(f"[bold red]Reasoner failed: {exc}[/bold red]")
            logger.exception("Reasoner failed")
            self._tracer.error("reasoner", error=exc)
            await self._send_event(self._tracer.events()[-1])
            return
        self._tracer.done("reasoner")
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.REASON)

    async def _review_reason(self) -> None:
        from decisionlab.agents.reasoner import Reasoner

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_reason

                assert self.emit is not None
                approved, rejections, formalizer_reruns = await review_reason(
                    self.state.reports_dir,
                    self.emit,
                )
            else:
                from decisionlab.feedback import review_reason

                approved, rejections, formalizer_reruns = await review_reason(
                    self.state.reports_dir,
                )
            if not rejections and not formalizer_reruns:
                # Group flat approved list by paradigm using selected_formulations
                approved_set = set(approved)
                self.state.approved_specs = {
                    paradigm: [f for f in fids if f in approved_set]
                    for paradigm, fids in self.state.selected_formulations.items()
                    if any(f in approved_set for f in fids)
                }
                break

            # Re-run Formalizer → Reasoner for paradigms with invalid formulations
            for paradigm_slug in formalizer_reruns:
                self.console.print(
                    f"[bold]Re-running Formalizer for '{paradigm_slug}'...[/bold]"
                )
                try:
                    from decisionlab.agents.formalizer import Formalizer

                    f = Formalizer(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("formalizer"),
                    )
                    await f.run([paradigm_slug])
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Formalizer re-run failed for '{paradigm_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Formalizer re-run failed for %s", paradigm_slug)
                    continue

                self.console.print(
                    f"[bold]Re-running Reasoner for '{paradigm_slug}'...[/bold]"
                )
                try:
                    r = Reasoner(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("reasoner"),
                    )
                    fids = self.state.selected_formulations.get(paradigm_slug, [])
                    await r.run({paradigm_slug: fids})
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Reasoner re-run failed for '{paradigm_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Reasoner re-run failed for %s", paradigm_slug)

            # Re-run Reasoner for each rejected paradigm (normal rejections)
            for _, paradigm_slug, _ in rejections:
                self.console.print(
                    f"[bold]Re-running Reasoner for '{paradigm_slug}'...[/bold]"
                )
                try:
                    r = Reasoner(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("reasoner"),
                    )
                    fids = self.state.selected_formulations.get(paradigm_slug, [])
                    await r.run({paradigm_slug: fids})
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Reasoner re-run failed for '{paradigm_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Reasoner re-run failed for %s", paradigm_slug)
            # Loop back to let user review again
            continue
        self.state.stage = Stage.BUILD

    async def _do_build(self) -> None:
        from decisionlab.agents.builder import Builder

        n_specs = sum(len(fs) for fs in self.state.approved_specs.values())
        self.console.print(f"[bold]Running Builder for {n_specs} spec(s)...[/bold]")
        self._tracer.agent("builder", "Builder", parent="reasoner")
        await self._send_event(self._tracer.events()[-1])
        try:
            b = Builder(
                client=self.client,
                models_prefix=self.state.models_prefix,
                run_id=self.state.run_id,
                project_root=self.project_root,
                **self._knowledge_tool_kwargs("builder"),
            )
            report = await b.run(self.state.approved_specs)
            self.state.build_results = report.results
            await self._validate_builder_files(self.state.approved_specs)
        except Exception as exc:
            self.console.print(f"[bold red]Builder failed: {exc}[/bold red]")
            logger.exception("Builder failed")
            self._tracer.error("builder", error=exc)
            await self._send_event(self._tracer.events()[-1])
            return
        self._tracer.done("builder")
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.BUILD)

    async def _review_build(self) -> None:
        import shared
        from decisionlab.agents.builder import Builder

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_build

                assert self.emit is not None
                _approved, rejections, reasoner_reruns = await review_build(
                    self.state.reports_dir,
                    self.state.build_results,
                    self.emit,
                )
            else:
                from decisionlab.feedback import review_build

                _approved, rejections, reasoner_reruns = await review_build(
                    self.state.reports_dir,
                    self.state.build_results,
                )
            if not rejections and not reasoner_reruns:
                await self._register_approved_models()
                self.state.stage = Stage.DONE
                return

            # Re-run Reasoner → Builder for paradigms with invalid builds
            for paradigm_slug in reasoner_reruns:
                self.console.print(
                    f"[bold]Re-running Reasoner for '{paradigm_slug}'...[/bold]"
                )
                try:
                    from decisionlab.agents.reasoner import Reasoner

                    r = Reasoner(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("reasoner"),
                    )
                    fids = self.state.selected_formulations.get(paradigm_slug, [])
                    await r.run({paradigm_slug: fids})
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Reasoner re-run failed for '{paradigm_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Reasoner re-run failed for %s", paradigm_slug)
                    continue

                self.console.print(
                    f"[bold]Re-running Builder for '{paradigm_slug}'...[/bold]"
                )
                try:
                    b = Builder(
                        client=self.client,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        project_root=self.project_root,
                        **self._knowledge_tool_kwargs("builder"),
                    )
                    paradigm_specs = self.state.approved_specs.get(paradigm_slug, [])
                    report = await b.run(
                        {paradigm_slug: paradigm_specs} if paradigm_specs else None
                    )
                    self.state.build_results.update(report.results)
                    # Clean up stale validation reports for this paradigm in S3
                    for sid in paradigm_specs:
                        await shared.storage.delete(
                            f"{self.state.models_prefix}/builder/{paradigm_slug}/{sid}_validation.json"
                        )
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Builder re-run failed for '{paradigm_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Builder re-run failed for %s", paradigm_slug)

            # Re-run Builder for each rejected build (normal rejections)
            for formulation_slug, paradigm_slug, _ in rejections:
                self.console.print(
                    f"[bold]Re-running Builder for '{formulation_slug}'...[/bold]"
                )
                try:
                    b = Builder(
                        client=self.client,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        project_root=self.project_root,
                        **self._knowledge_tool_kwargs("builder"),
                    )
                    report = await b.run({paradigm_slug: [formulation_slug]})
                    self.state.build_results.update(report.results)
                except Exception as exc:
                    self.console.print(
                        f"[bold red]Builder re-run failed for '{formulation_slug}': {exc}[/bold red]"
                    )
                    logger.exception("Builder re-run failed for %s", formulation_slug)
            # Loop back to let user review again
            continue

    # -- filename validation ---------------------------------------------------

    async def _validate_reasoner_files(
        self,
        selected: dict[str, list[str]],
    ) -> None:
        """Verify expected reasoner files exist; rename mismatches."""
        import shared

        prefix = f"{self.state.models_prefix}/reasoner/"
        for paradigm, formulations in selected.items():
            for formulation in formulations:
                expected = f"{prefix}{paradigm}/{formulation}.json"
                if await shared.storage.exists(expected):
                    continue
                # Try to find a misnamed file in the paradigm dir
                paradigm_prefix = f"{prefix}{paradigm}/"
                keys = await shared.storage.list(paradigm_prefix)
                json_keys = [k for k in keys if k.endswith(".json")]
                if json_keys:
                    old_key = json_keys[0]
                    await shared.storage.rename(old_key, expected)
                    logger.warning(
                        "Reasoner file renamed: %s → %s",
                        old_key,
                        expected,
                    )
                else:
                    logger.warning("Reasoner file missing: %s", expected)

    async def _validate_builder_files(
        self,
        approved_specs: dict[str, list[str]],
    ) -> None:
        """Verify expected builder files exist; rename mismatches."""
        import shared

        prefix = f"{self.state.models_prefix}/builder/"
        for paradigm, formulations in approved_specs.items():
            for formulation in formulations:
                expected = f"{prefix}{paradigm}/{formulation}_model.py"
                if await shared.storage.exists(expected):
                    continue
                paradigm_prefix = f"{prefix}{paradigm}/"
                keys = await shared.storage.list(paradigm_prefix)
                model_keys = [k for k in keys if k.endswith("_model.py")]
                if model_keys:
                    old_key = model_keys[0]
                    await shared.storage.rename(old_key, expected)
                    logger.warning(
                        "Builder file renamed: %s → %s",
                        old_key,
                        expected,
                    )
                else:
                    logger.warning("Builder file missing: %s", expected)

    async def _register_approved_models(self) -> None:
        """Insert or update Model rows in Postgres for each approved build."""
        from sqlalchemy import select

        import shared
        from shared.models import Model

        run_uuid = uuid.UUID(self.state.run_id)

        async with shared.db.get_session() as session:
            for paradigm, formulations in self.state.approved_specs.items():
                for formulation in formulations:
                    s3_model_key = (
                        f"{self.state.models_prefix}/builder/"
                        f"{paradigm}/{formulation}_model.py"
                    )
                    s3_test_key = (
                        f"{self.state.models_prefix}/builder/"
                        f"{paradigm}/test_{formulation}.py"
                    )

                    # Read model source to extract class_name
                    try:
                        source = await shared.storage.get_text(s3_model_key)
                    except Exception:
                        logger.warning(
                            "Model file not found in S3: %s — skipping registration",
                            s3_model_key,
                        )
                        continue

                    match = re.search(r"class\s+(\w+)", source)
                    class_name = match.group(1) if match else "Unknown"

                    # Upsert: update if exists (re-run), insert otherwise
                    result = await session.execute(
                        select(Model).where(
                            Model.run_id == run_uuid,
                            Model.paradigm == paradigm,
                            Model.formulation == formulation,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.class_name = class_name
                        existing.s3_model_key = s3_model_key
                        existing.s3_test_key = s3_test_key
                        logger.info(
                            "Updated Model row for %s/%s",
                            paradigm,
                            formulation,
                        )
                    else:
                        session.add(
                            Model(
                                run_id=run_uuid,
                                paradigm=paradigm,
                                formulation=formulation,
                                class_name=class_name,
                                s3_model_key=s3_model_key,
                                s3_test_key=s3_test_key,
                            )
                        )
                        logger.info(
                            "Registered Model for %s/%s",
                            paradigm,
                            formulation,
                        )

            await session.commit()

    async def _execute_rerun_cascade(self, rerun: RerunRequest) -> None:
        """Run the cascade of agents from *rerun.target* down to builder."""
        paradigm = rerun.paradigm
        cascade_order = ["researcher", "formalizer", "reasoner", "builder"]
        start_idx = cascade_order.index(rerun.target)
        stages_to_run = cascade_order[start_idx:]

        for stage_name in stages_to_run:
            try:
                if stage_name == "researcher":
                    from decisionlab.agents.deep_researcher import DeepResearcher

                    self.console.print(
                        f"[bold]Cascade: DeepResearcher for '{paradigm}'...[/bold]"
                    )
                    dr = DeepResearcher(
                        client=self.client,
                        search=self.search,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("deep_researcher"),
                    )
                    await dr.run(paradigm)

                elif stage_name == "formalizer":
                    from decisionlab.agents.formalizer import Formalizer

                    self.console.print(
                        f"[bold]Cascade: Formalizer for '{paradigm}'...[/bold]"
                    )
                    f = Formalizer(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("formalizer"),
                    )
                    await f.run([paradigm])

                elif stage_name == "reasoner":
                    from decisionlab.agents.reasoner import Reasoner

                    self.console.print(
                        f"[bold]Cascade: Reasoner for '{paradigm}'...[/bold]"
                    )
                    r = Reasoner(
                        client=self.client,
                        research_prefix=self.state.research_prefix,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        **self._knowledge_tool_kwargs("reasoner"),
                    )
                    fids = self.state.selected_formulations.get(paradigm, [])
                    await r.run({paradigm: fids})

                elif stage_name == "builder":
                    from decisionlab.agents.builder import Builder

                    self.console.print(
                        f"[bold]Cascade: Builder for '{paradigm}'...[/bold]"
                    )
                    b = Builder(
                        client=self.client,
                        models_prefix=self.state.models_prefix,
                        run_id=self.state.run_id,
                        project_root=self.project_root,
                        **self._knowledge_tool_kwargs("builder"),
                    )
                    # Build only specs belonging to this paradigm
                    paradigm_specs = self.state.approved_specs.get(paradigm, [])
                    report = await b.run(
                        {paradigm: paradigm_specs} if paradigm_specs else None
                    )
                    self.state.build_results.update(report.results)

            except Exception as exc:
                self.console.print(
                    f"[bold red]Cascade: {stage_name} failed for '{paradigm}': {exc}[/bold red]"
                )
                logger.exception("Cascade %s failed for %s", stage_name, paradigm)
                return  # abort cascade on failure
