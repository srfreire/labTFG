"""Pipeline orchestration and human feedback routing."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from anthropic import AsyncAnthropic
from rich.console import Console

from decisionlab.domain.models import RerunRequest
from decisionlab.domain.ports import WebSearchPort
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    create_retrieve_knowledge,
)
from decisionlab.parsing import FORMULATION_HEADER_RE
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from decisionlab.agents.memory_agent import MemoryAgent

logger = logging.getLogger(__name__)

# Type alias for the emit callback (async)
EmitFn = Callable[[dict], Awaitable[None]]

# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    RESEARCH = "research"
    REVIEW_RESEARCH = "review_research"
    FORMALIZE = "formalize"
    REVIEW_FORMALIZE = "review_formalize"
    GET_ENV_SPEC = "get_env_spec"
    REASON = "reason"
    REVIEW_REASON = "review_reason"
    BUILD = "build"
    REVIEW_BUILD = "review_build"
    DONE = "done"


# Stages after which the Memory Agent should run
_MEMORY_STAGES = {
    Stage.RESEARCH: "researcher",
    Stage.FORMALIZE: "formalizer",
    Stage.REASON: "reasoner",
    Stage.BUILD: "builder",
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
            raise FileNotFoundError(f"Pipeline state not found at s3://{key}")

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
                candidates.append(f"{self.models_prefix}/reasoner/{paradigm}/{fid}.json")
        for paradigm, fids in self.approved_specs.items():
            for fid in fids:
                candidates.append(f"{self.models_prefix}/builder/{paradigm}/{fid}_model.py")

        missing: list[str] = []
        for key in candidates:
            try:
                if not await shared.storage.exists(key):
                    missing.append(key)
            except Exception:
                # Storage unreachable → don't pretend the artifact is missing;
                # let the caller surface the connection error elsewhere.
                logger.warning("S3 reachability check failed for %s", key, exc_info=True)
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
    ):
        self.client = client
        self.state = state
        self.search = search
        self.project_root = project_root
        self.console = Console()
        self.emit = emit  # None → CLI mode; set → web mode
        self._web_mode = emit is not None
        self.memory_agent: MemoryAgent | None = self._init_memory_agent()
        # Tracks fire-and-forget Memory Agent ticks so they don't get GC'd
        # mid-flight; each task removes itself via done_callback.
        self._background_tasks: set[asyncio.Task] = set()

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
            from decisionlab.agents.memory_agent import MemoryAgent as MA

            return MA(
                client=self.client,
                kg=getattr(shared, "kg", None),
                vector_store=getattr(shared, "vectors", None),
                embedding_service=getattr(shared, "embeddings", None),
                db=shared.db,
            )
        except Exception:
            logger.debug("Knowledge infrastructure unavailable — Memory Agent disabled")
            return None

    async def _emit(self, msg: dict) -> None:
        """Send an event to the frontend (no-op in CLI mode)."""
        if self.emit is not None:
            await self.emit(msg)

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
        await self._emit({"type": "agents", "agents": agents})

    # -- DB helpers -----------------------------------------------------------

    async def _update_run(self, **values) -> None:
        """Update the Run row in Postgres with the given column values."""
        import shared
        from shared.models import Run
        from sqlalchemy import update

        async with shared.db.get_session() as session:
            await session.execute(
                update(Run)
                .where(Run.id == uuid.UUID(self.state.run_id))
                .values(**values)
            )
            await session.commit()

    # -- memory agent ---------------------------------------------------------

    async def _run_memory_agent(self, stage: Stage) -> None:
        """Run the Memory Agent after a successful work stage. Never blocks pipeline."""
        stage_name = _MEMORY_STAGES[stage]
        try:
            output = await self._collect_stage_output(stage)
            result = await self.memory_agent.run(
                stage_name, output, self.state.run_id, emit=self.emit
            )
            logger.info("Memory Agent [%s] completed: %s", stage_name, result)
        except Exception:
            logger.exception(
                "Memory Agent failed for stage=%s — continuing pipeline", stage_name
            )

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
        """Read the stage's output artifacts from S3."""
        import shared

        prefix = self.state.research_prefix
        models = self.state.models_prefix

        if stage == Stage.RESEARCH:
            key = f"{prefix}/report.md"
            try:
                return await shared.storage.get_text(key)
            except Exception:
                logger.warning("Could not read research report from %s", key)
                return ""

        if stage == Stage.FORMALIZE:
            parts: list[str] = []
            for slug in self.state.approved_paradigms:
                key = f"{prefix}/formulations/{slug}.md"
                try:
                    parts.append(await shared.storage.get_text(key))
                except Exception:
                    logger.warning("Could not read formulation %s", key)
            return "\n\n".join(parts)

        if stage == Stage.REASON:
            parts = []
            for paradigm, fids in self.state.selected_formulations.items():
                for fid in fids:
                    key = f"{models}/reasoner/{paradigm}/{fid}.json"
                    try:
                        parts.append(await shared.storage.get_text(key))
                    except Exception:
                        logger.warning("Could not read reasoner spec %s", key)
            return "\n\n".join(parts)

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
            return "\n\n".join(parts)

        return ""

    # -- main loop -----------------------------------------------------------

    async def run(self) -> None:
        handlers = {
            Stage.RESEARCH: self._do_research,
            Stage.REVIEW_RESEARCH: self._review_research,
            Stage.FORMALIZE: self._do_formalize,
            Stage.REVIEW_FORMALIZE: self._review_formalize,
            Stage.GET_ENV_SPEC: self._get_env_spec,
            Stage.REASON: self._do_reason,
            Stage.REVIEW_REASON: self._review_reason,
            Stage.BUILD: self._do_build,
            Stage.REVIEW_BUILD: self._review_build,
        }

        # Emit agent list so the frontend knows which agents are available
        await self._emit_agents()

        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]
            await self._emit(
                {
                    "type": "stage_change",
                    "stage": current_stage.value,
                    "status": "running",
                }
            )
            await handler()

            # Emit stage-done BEFORE kicking off the Memory Agent so the UI can
            # show the review stage and the memory tick running in parallel.
            await self._emit(
                {
                    "type": "stage_change",
                    "stage": current_stage.value,
                    "status": "done",
                }
            )
            await self.state.save()
            await self._update_run(status=self.state.stage.value)

            # Memory Agent post-hook: fires concurrently with the following
            # review stage. The frontend disables "Continue" until the agent
            # emits ``status=done``, so the user can't advance past a review
            # before the memory tick finishes.
            stage_advanced = self.state.stage != current_stage
            if (
                stage_advanced
                and current_stage in _MEMORY_STAGES
                and self.memory_agent is not None
            ):
                task = asyncio.create_task(self._run_memory_agent(current_stage))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

        # Drain any in-flight Memory Agent ticks before claiming the run is
        # done. This makes "pipeline complete" mean "memories written or at
        # least attempted", not just "memories scheduled" — and gives the
        # following consolidation step a stable view of the run's memories.
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Finalize run: consolidation + s3_report_key
        if self.state.stage == Stage.DONE:
            if self.memory_agent is not None:
                await self._run_consolidation()
            await self._update_run(
                s3_report_key=f"{self.state.research_prefix}/report.md",
            )

    # -- stage handlers ------------------------------------------------------

    async def _do_research(self) -> None:
        from decisionlab.agents.researcher import Researcher

        self.console.print("[bold]Running Researcher...[/bold]")
        await self._emit(
            {
                "type": "node_add",
                "node": {
                    "id": "researcher",
                    "kind": "agent",
                    "label": "Researcher",
                    "status": "running",
                },
            }
        )
        try:
            r = Researcher(
                client=self.client,
                search=self.search,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("researcher"),
            )
            await r.run(self.state.problem)
        except Exception as exc:
            self.console.print(f"[bold red]Researcher failed: {exc}[/bold red]")
            logger.exception("Researcher failed")
            await self._emit(
                {"type": "node_update", "id": "researcher", "status": "error"}
            )
            return  # stay at current stage
        await self._emit({"type": "node_update", "id": "researcher", "status": "done"})
        self.state.stage = Stage.REVIEW_RESEARCH

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
        await self._emit(
            {
                "type": "node_add",
                "node": {
                    "id": "formalizer",
                    "kind": "agent",
                    "label": "Formalizer",
                    "status": "running",
                },
            }
        )
        await self._emit(
            {
                "type": "edge_add",
                "edge": {"source": "researcher", "target": "formalizer"},
            }
        )
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
            await self._emit(
                {"type": "node_update", "id": "formalizer", "status": "error"}
            )
            return
        await self._emit({"type": "node_update", "id": "formalizer", "status": "done"})
        self.state.stage = Stage.REVIEW_FORMALIZE

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
        await self._emit(
            {
                "type": "node_add",
                "node": {
                    "id": "reasoner",
                    "kind": "agent",
                    "label": "Reasoner",
                    "status": "running",
                },
            }
        )
        await self._emit(
            {"type": "edge_add", "edge": {"source": "formalizer", "target": "reasoner"}}
        )
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
            await self._emit(
                {"type": "node_update", "id": "reasoner", "status": "error"}
            )
            return
        await self._emit({"type": "node_update", "id": "reasoner", "status": "done"})
        self.state.stage = Stage.REVIEW_REASON

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
        await self._emit(
            {
                "type": "node_add",
                "node": {
                    "id": "builder",
                    "kind": "agent",
                    "label": "Builder",
                    "status": "running",
                },
            }
        )
        await self._emit(
            {"type": "edge_add", "edge": {"source": "reasoner", "target": "builder"}}
        )
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
            await self._emit(
                {"type": "node_update", "id": "builder", "status": "error"}
            )
            return
        await self._emit({"type": "node_update", "id": "builder", "status": "done"})
        self.state.stage = Stage.REVIEW_BUILD

    async def _review_build(self) -> None:
        import shared
        from decisionlab.agents.builder import Builder

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_build

                assert self.emit is not None
                approved, rejections, reasoner_reruns = await review_build(
                    self.state.reports_dir,
                    self.state.build_results,
                    self.emit,
                )
            else:
                from decisionlab.feedback import review_build

                approved, rejections, reasoner_reruns = await review_build(
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
        import shared
        from shared.models import Model
        from sqlalchemy import select

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
