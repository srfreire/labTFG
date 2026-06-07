"""Pipeline orchestration and human feedback routing."""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import agrex
from rich.console import Console

from decisionlab.domain.models import RerunRequest
from decisionlab.feedback_port import CLIFeedback, FeedbackPort
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    create_retrieve_knowledge,
)
from decisionlab.parsing import FORMULATION_HEADER_RE
from decisionlab.runtime import agrex_context
from decisionlab.runtime.tool_calls import set_stage as _set_recording_stage
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from decisionlab.agents.memory_agent import MemoryAgent
    from decisionlab.domain.ports import WebSearchPort
    from shared.services import Services

logger = logging.getLogger(__name__)

# Type alias for the emit callback (async)
EmitFn = Callable[[dict], Awaitable[None]]

# ---------------------------------------------------------------------------
# Stage enum
# ---------------------------------------------------------------------------


class Stage(StrEnum):
    CLASSIFY_UMBRELLA = "classify_umbrella"
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

# Mapping work stage → its dedicated MEMORY_X stage. Review handlers advance
# to MEMORY_X when memory infra is available, so the backbone only records
# accepted output rather than raw candidates.
_MEMORY_STAGE_OF = {
    Stage.RESEARCH: Stage.MEMORY_RESEARCH,
    Stage.FORMALIZE: Stage.MEMORY_FORMALIZE,
    Stage.REASON: Stage.MEMORY_REASON,
    Stage.BUILD: Stage.MEMORY_BUILD,
}

# Mapping MEMORY_X → the work stage it follows (used by _memory_<stage>
# handlers to look up the right output text and agent name).
_WORK_STAGE_OF_MEMORY = {v: k for k, v in _MEMORY_STAGE_OF.items()}

# Mapping MEMORY_X → the REVIEW_X that gates the work stage.
_REVIEW_STAGE_OF_MEMORY = {
    Stage.MEMORY_RESEARCH: Stage.REVIEW_RESEARCH,
    Stage.MEMORY_FORMALIZE: Stage.REVIEW_FORMALIZE,
    Stage.MEMORY_REASON: Stage.REVIEW_REASON,
    Stage.MEMORY_BUILD: Stage.REVIEW_BUILD,
}

# Mapping MEMORY_X → the next pipeline stage after accepted output has been
# committed to memory/KG.
_NEXT_AFTER_MEMORY = {
    Stage.MEMORY_RESEARCH: Stage.FORMALIZE,
    Stage.MEMORY_FORMALIZE: Stage.GET_ENV_SPEC,
    Stage.MEMORY_REASON: Stage.BUILD,
    Stage.MEMORY_BUILD: Stage.DONE,
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

# Cap on consecutive iterations of `_run_loop` that observe the same stage
# without progress. Work-stage handlers `_do_research / _do_formalize /
# _do_reason / _do_build` (and `_get_env_spec`) catch agent failures and
# return without advancing `state.stage`, which is fine when a human is
# driving (Ctrl-C). Non-interactive callers (the eval harness, the web
# server) have no break-point, so a persistent agent failure (auth error,
# network outage) would loop forever and burn API quota. Aborting after
# this many tries is a hard safety floor — overridable per-process via
# the `DECISIONLAB_MAX_STAGE_RETRIES` env var.
_MAX_STAGE_RETRIES = 3


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

    # Output of the upstream umbrella classifier — in-memory only (not
    # persisted on the Run JSON column or the WS payload). Resumed runs
    # re-classify on the next start; the cost is one Haiku call.
    umbrella: object | None = None  # UmbrellaDecision | None

    # -- S3 prefix helpers ---------------------------------------------------

    @property
    def research_prefix(self) -> str:
        return f"research/{self.run_id}"

    @property
    def models_prefix(self) -> str:
        return f"models/{self.run_id}"

    # -- persistence ---------------------------------------------------------

    async def save(self, services: Services) -> None:
        """Save state to S3 at research/{run_id}/pipeline_state.json."""
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
        await services.storage.put_text(key, json.dumps(data, indent=2))
        logger.debug("PipelineState saved to s3://%s", key)

    @classmethod
    async def load(cls, run_id: str, services: Services) -> PipelineState:
        """Load state from S3 and verify referenced artifacts still exist.

        Raises ``FileNotFoundError`` when the state file itself is missing,
        or ``RuntimeError`` when the state references artifacts (formulation
        markdown, reasoner specs, builder models) that are not on S3 — which
        usually means a previous run crashed mid-stage and left the state
        ahead of the actual outputs.
        """
        key = f"research/{run_id}/pipeline_state.json"
        try:
            raw = await services.storage.get_text(key)
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

        missing = await state._missing_artifacts(services)
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

    async def _missing_artifacts(self, services: Services) -> list[str]:
        """Return S3 keys this state references that don't exist on the bucket.

        Walks the artifacts implied by each filled-in state field. Empty fields
        are skipped (a state in early RESEARCH has nothing to validate beyond
        itself). Returns an empty list when state is coherent.
        """
        candidates: list[str] = []
        formulation_ready_stages = {
            Stage.MEMORY_FORMALIZE,
            Stage.REVIEW_FORMALIZE,
            Stage.GET_ENV_SPEC,
            Stage.REASON,
            Stage.MEMORY_REASON,
            Stage.REVIEW_REASON,
            Stage.BUILD,
            Stage.MEMORY_BUILD,
            Stage.REVIEW_BUILD,
            Stage.DONE,
        }
        reason_ready_stages = {
            Stage.MEMORY_REASON,
            Stage.REVIEW_REASON,
            Stage.BUILD,
            Stage.MEMORY_BUILD,
            Stage.REVIEW_BUILD,
            Stage.DONE,
        }
        build_ready_stages = {
            Stage.MEMORY_BUILD,
            Stage.REVIEW_BUILD,
            Stage.DONE,
        }

        if self.stage in formulation_ready_stages:
            for slug in self.approved_paradigms:
                candidates.append(f"{self.research_prefix}/formulations/{slug}.md")
        if self.stage in reason_ready_stages:
            for paradigm, fids in self.selected_formulations.items():
                for fid in fids:
                    candidates.append(
                        f"{self.models_prefix}/reasoner/{paradigm}/{fid}.json"
                    )
        if self.stage in build_ready_stages:
            for paradigm, fids in self.approved_specs.items():
                for fid in fids:
                    candidates.append(
                        f"{self.models_prefix}/builder/{paradigm}/{fid}_model.py"
                    )

        missing: list[str] = []
        for key in candidates:
            try:
                if not await services.storage.exists(key):
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
    services: Services,
) -> dict[str, list[str]]:
    """Convert ``{slug: [int]}`` from feedback to ``{slug: [formulation_slug]}``."""
    converted: dict[str, list[str]] = {}
    for slug, kept_numbers in raw_selected.items():
        if not kept_numbers:
            converted[slug] = []
            continue
        key = f"research/{state.run_id}/formulations/{slug}.md"
        try:
            text = await services.storage.get_text(key)
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
        *,
        services: Services,
        emit: EmitFn | None = None,
        stop_after: Stage | None = None,
        feedback: FeedbackPort | None = None,
    ):
        self.client = client
        self.state = state
        self.search = search
        self.project_root = project_root
        self._services: Services = services
        self.console = Console()
        self.emit = emit  # None → no UI mirroring of trace events
        # Feedback port: defaults to CLIFeedback (questionary). The web server
        # passes WebFeedback(emit); the eval harness passes AutoApproveFeedback.
        self.feedback: FeedbackPort = (
            feedback if feedback is not None else CLIFeedback()
        )
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
            _REVIEW_STAGE_OF_MEMORY[_MEMORY_STAGE_OF[stop_after]]
            if stop_after is not None
            else None
        )
        self._tracer: agrex.Tracer | None = None
        self._trace_local_path: Path | None = None
        self._trace_nodes: set[str] = set()
        self._trace_edges: set[str] = set()
        # In-memory mirror of `_record_memory_result` payloads, keyed by stage
        # name ("researcher"/"formalizer"/"reasoner"/"builder"). Lets in-process
        # callers (e.g. the eval runner) read per-stage memory results without
        # round-tripping the database.
        self.memory_results: dict[str, dict] = {}

    @staticmethod
    def _trace_id(*parts: str) -> str:
        raw = ":".join(str(p) for p in parts if p is not None)
        return raw.replace("/", ":").replace(" ", "-")

    async def _trace_last(self) -> None:
        if self._tracer is None:
            return
        events = self._tracer.events()
        if events:
            await self._send_event(events[-1])

    async def _trace_node_once(
        self,
        node_type: str,
        node_id: str,
        label: str,
        *,
        parent: str | None = None,
        status: str = "done",
        metadata: dict | None = None,
    ) -> None:
        if self._tracer is None or node_id in self._trace_nodes:
            return
        self._trace_nodes.add(node_id)
        node_metadata = dict(metadata or {})
        if status == "running":
            node_metadata.setdefault("startedAt", agrex_context.now_ms())
        metadata_arg = node_metadata or None
        if node_type == "agent":
            self._tracer.agent(
                node_id, label, parent=parent, status=status, metadata=metadata_arg
            )
        elif node_type == "sub_agent":
            self._tracer.sub_agent(
                node_id, label, parent=parent, status=status, metadata=metadata_arg
            )
        elif node_type == "tool":
            self._tracer.tool(
                node_id, label, parent=parent, status=status, metadata=metadata_arg
            )
        elif node_type == "file":
            self._tracer.file(
                node_id, label, parent=parent, status=status, metadata=metadata_arg
            )
        else:
            self._tracer.node(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": label,
                    "parentId": parent,
                    "status": status,
                    "metadata": metadata_arg or {},
                }
            )
        await self._trace_last()

    async def _trace_edge_once(
        self,
        source: str,
        target: str,
        *,
        edge_type: str = "relates",
        label: str | None = None,
    ) -> None:
        if self._tracer is None:
            return
        edge_id = self._trace_id("edge", source, edge_type, target)
        if edge_id in self._trace_edges:
            return
        self._trace_edges.add(edge_id)
        self._tracer.edge(
            id=edge_id, source=source, target=target, type=edge_type, label=label
        )
        await self._trace_last()

    async def _trace_file_artifact(
        self,
        key: str,
        *,
        parent: str,
        artifact_type: str,
        label: str | None = None,
    ) -> str:
        node_id = self._trace_id("file", key)
        await self._trace_node_once(
            "file",
            node_id,
            label or Path(key).name,
            parent=parent,
            status="done",
            metadata={"s3_key": key, "artifact_type": artifact_type},
        )
        await self._trace_edge_once(parent, node_id, edge_type="writes", label="writes")
        return node_id

    def _knowledge_tool_kwargs(self, stage: str) -> dict:
        """Return keyword args for knowledge tool injection into an agent.

        Returns ``{"knowledge_tool_schema": ..., "knowledge_tool_handler": ...}``
        when knowledge infrastructure is available, otherwise an empty dict
        (agent runs without the tool — graceful degradation).
        """
        try:
            kg = self._services.kg
            vectors = self._services.vectors
            embeddings = self._services.embeddings

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
                db=self._services.db,
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
            if self._services.db is None:
                return None
            from decisionlab.agents.memory_agent import MemoryAgent

            return MemoryAgent(
                client=self.client,
                kg=self._services.kg,
                vector_store=self._services.vectors,
                embedding_service=self._services.embeddings,
                db=self._services.db,
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

                if self._services.storage is not None:
                    key = f"research/{run_id}/trace.jsonl"
                    await self._services.storage.put_text(key, content)
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

    async def _trace_research_artifacts(self) -> None:
        prefix = self.state.research_prefix
        await self._trace_file_artifact(
            f"{prefix}/report.md", parent="researcher", artifact_type="report"
        )
        keys = await self._services.storage.list(f"{prefix}/deep/")
        for key in sorted(k for k in keys if k.endswith(".md")):
            slug = Path(key).stem
            sub_id = self._trace_id("deep_researcher", slug)
            await self._trace_node_once(
                "sub_agent",
                sub_id,
                f"DeepResearcher: {slug}",
                parent="researcher",
                status="done",
                metadata={"paradigm": slug},
            )
            await self._trace_edge_once(
                "researcher", sub_id, edge_type="launches", label="launches"
            )
            await self._trace_file_artifact(
                key, parent=sub_id, artifact_type="deep_report"
            )

    async def _trace_formalization_artifacts(self) -> None:
        prefix = f"{self.state.research_prefix}/formulations/"
        keys = await self._services.storage.list(prefix)
        for key in sorted(k for k in keys if k.endswith(".md")):
            slug = Path(key).stem
            sub_id = self._trace_id("formalizer", slug)
            await self._trace_node_once(
                "sub_agent",
                sub_id,
                f"FormalizerSubAgent: {slug}",
                parent="formalizer",
                status="done",
                metadata={"paradigm": slug},
            )
            await self._trace_edge_once(
                "formalizer", sub_id, edge_type="launches", label="launches"
            )
            await self._trace_file_artifact(
                key, parent=sub_id, artifact_type="formulation"
            )

    async def _trace_selected_formulations(self) -> None:
        for paradigm, formulations in sorted(self.state.selected_formulations.items()):
            for formulation in formulations:
                node_id = self._trace_id("formulation", paradigm, formulation)
                await self._trace_node_once(
                    "artifact",
                    node_id,
                    formulation,
                    parent=self._trace_id("formalizer", paradigm),
                    status="done",
                    metadata={
                        "artifact_type": "formulation_selection",
                        "paradigm": paradigm,
                        "formulation": formulation,
                    },
                )

    async def _trace_env_spec_artifact(self) -> None:
        await self._trace_file_artifact(
            f"{self.state.research_prefix}/env_spec.json",
            parent="reasoner",
            artifact_type="env_spec",
        )

    async def _trace_reasoner_artifacts(self) -> None:
        for paradigm, formulations in sorted(self.state.selected_formulations.items()):
            sub_id = self._trace_id("reasoner", paradigm)
            await self._trace_node_once(
                "sub_agent",
                sub_id,
                f"ReasonerSubAgent: {paradigm}",
                parent="reasoner",
                status="done",
                metadata={"paradigm": paradigm},
            )
            await self._trace_edge_once(
                "reasoner", sub_id, edge_type="launches", label="launches"
            )
            for formulation in formulations:
                key = (
                    f"{self.state.models_prefix}/reasoner/{paradigm}/{formulation}.json"
                )
                await self._trace_file_artifact(
                    key, parent=sub_id, artifact_type="reasoner_spec"
                )

    async def _trace_builder_artifacts(self) -> None:
        for paradigm, formulations in sorted(self.state.approved_specs.items()):
            for formulation in formulations:
                sub_id = self._trace_id("builder", paradigm, formulation)
                await self._trace_node_once(
                    "sub_agent",
                    sub_id,
                    f"BuilderSubAgent: {formulation}",
                    parent="builder",
                    status="done",
                    metadata={"paradigm": paradigm, "formulation": formulation},
                )
                await self._trace_edge_once(
                    "builder", sub_id, edge_type="launches", label="launches"
                )
                base = f"{self.state.models_prefix}/builder/{paradigm}"
                await self._trace_file_artifact(
                    f"{base}/{formulation}_model.py",
                    parent=sub_id,
                    artifact_type="model",
                )
                await self._trace_file_artifact(
                    f"{base}/test_{formulation}.py",
                    parent=sub_id,
                    artifact_type="test",
                )

    # -- DB helpers -----------------------------------------------------------

    async def _update_run(self, **values) -> None:
        """Update the Run row in Postgres with the given column values."""
        from sqlalchemy import update

        from shared.models import Run

        async with self._services.db.get_session() as session:
            await session.execute(
                update(Run)
                .where(Run.id == uuid.UUID(self.state.run_id))
                .values(**values)
            )
            await session.commit()

    # -- memory agent ---------------------------------------------------------

    def _next_after_work(self, work_stage: Stage) -> Stage:
        """Stage to transition to after a work handler succeeds."""
        memory_stage = _MEMORY_STAGE_OF[work_stage]
        return _REVIEW_STAGE_OF_MEMORY[memory_stage]

    def _next_after_review(self, review_stage: Stage) -> Stage:
        """Stage to transition to after a review accepts output."""
        memory_stage = {
            review: memory for memory, review in _REVIEW_STAGE_OF_MEMORY.items()
        }[review_stage]
        if self.memory_agent is None:
            return _NEXT_AFTER_MEMORY[memory_stage]
        return memory_stage

    async def _run_memory_stage(self, memory_stage: Stage) -> None:
        """Body of every _memory_<stage> handler. Awaits the Memory Agent
        synchronously, persists the per-stage result (or error) on the run
        row, then advances to the next pipeline stage. Failures never block
        the pipeline — they're recorded for post-hoc inspection via the
        runs.memory_results JSONB column."""
        work_stage = _WORK_STAGE_OF_MEMORY[memory_stage]
        next_stage = _NEXT_AFTER_MEMORY[memory_stage]
        agent_name = _MEMORY_AGENT_STAGE_NAMES[work_stage]

        if self.memory_agent is None:
            self.state.stage = next_stage
            return

        memory_node_id = self._trace_id("memory_agent", agent_name)
        await self._trace_node_once(
            "sub_agent",
            memory_node_id,
            f"MemoryAgent: {agent_name}",
            parent=_MEMORY_AGENT_STAGE_NAMES[work_stage],
            status="running",
            metadata={"source_stage": agent_name},
        )
        await self._trace_edge_once(
            _MEMORY_AGENT_STAGE_NAMES[work_stage],
            memory_node_id,
            edge_type="extracts",
            label="extracts",
        )

        payload: dict
        try:
            output = await self._collect_stage_output(work_stage)
            approved_specs = (
                self.state.approved_specs or self.state.selected_formulations
            )
            result = await self.memory_agent.run(
                agent_name,
                output,
                self.state.run_id,
                emit=self.emit,
                approved_paradigms=self.state.approved_paradigms,
                approved_specs=approved_specs,
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
            if result.kg_errors:
                payload["kg_errors"] = result.kg_errors
                payload["kg_error_count"] = len(result.kg_errors)
            if result.kg_health is not None:
                payload["kg_health"] = asdict(result.kg_health)
            if result.kg_review is not None:
                payload["kg_review"] = asdict(result.kg_review)
        except Exception as exc:
            logger.exception(
                "Memory Agent failed for stage=%s — continuing pipeline",
                agent_name,
            )
            payload = {"status": "failed", "error": str(exc)}

        await self._record_memory_result(agent_name, payload)
        if payload.get("status") == "ok":
            await self._trace_memory_outputs(memory_node_id, agent_name, payload)
            self._tracer.done(
                memory_node_id,
                metadata={**payload, "endedAt": agrex_context.now_ms()},
            )
        else:
            self._tracer.error(
                memory_node_id,
                error=payload.get("error"),
                metadata={**payload, "endedAt": agrex_context.now_ms()},
            )
        await self._trace_last()
        self.state.stage = next_stage

    async def _trace_memory_outputs(
        self, memory_node_id: str, agent_name: str, payload: dict
    ) -> None:
        kg_node = self._trace_id("memory_output", agent_name, "kg")
        await self._trace_node_once(
            "artifact",
            kg_node,
            f"KG writes: {agent_name}",
            parent=memory_node_id,
            status="done",
            metadata={
                "nodes_created": payload.get("nodes_created", 0),
                "nodes_merged": payload.get("nodes_merged", 0),
                "relations_created": payload.get("relations_created", 0),
            },
        )
        await self._trace_edge_once(
            memory_node_id, kg_node, edge_type="writes", label="KG"
        )

        facts_node = self._trace_id("memory_output", agent_name, "facts")
        await self._trace_node_once(
            "artifact",
            facts_node,
            f"Memories: {agent_name}",
            parent=memory_node_id,
            status="done",
            metadata={
                "facts_stored": payload.get("facts_stored", 0),
                "duplicates_skipped": payload.get("duplicates_skipped", 0),
                "conflicts_resolved": payload.get("conflicts_resolved", 0),
            },
        )
        await self._trace_edge_once(
            memory_node_id, facts_node, edge_type="indexes", label="indexes"
        )

    async def _record_memory_result(self, agent_name: str, payload: dict) -> None:
        """Merge a per-stage Memory Agent result into runs.memory_results.
        Read-modify-write is fine here: the Router is the sole writer for any
        given run, so there's no concurrent-update race to worry about."""
        from shared.models import Run

        self.memory_results[agent_name] = payload

        try:
            async with self._services.db.get_session() as session:
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
        from decisionlab.eval.timing import record_stage

        async with record_stage("consolidation"):
            try:
                from decisionlab.knowledge.consolidation import consolidate

                if (
                    self._services.db is None
                    or self._services.embeddings is None
                    or self._services.vectors is None
                ):
                    return

                async with self._services.db.get_session() as session:
                    result = await consolidate(
                        db_session=session,
                        embedding_service=self._services.embeddings,
                        vector_store=self._services.vectors,
                        client=self.client,
                        run_id=self.state.run_id,
                        kg=self._services.kg,
                    )
                logger.info("Consolidation completed: %s", result)
            except Exception:
                logger.exception("Consolidation failed — continuing pipeline")

    async def _collect_stage_output(self, stage: Stage) -> str:
        """Return the stage's output text.

        Research memory uses approved deep reports when available; otherwise
        the method prefers the in-memory cache populated by the work handler
        before falling back to S3 for resumed runs and uncached stages.
        """
        prefix = self.state.research_prefix
        models = self.state.models_prefix

        if stage == Stage.RESEARCH:
            parts: list[str] = []
            if self.state.approved_paradigms:
                for slug in self.state.approved_paradigms:
                    key = f"{prefix}/deep/{slug}.md"
                    try:
                        parts.append(await self._services.storage.get_text(key))
                    except Exception:
                        logger.warning("Could not read approved deep report %s", key)
            else:
                cached = self._stage_outputs.get(stage)
                if cached is not None:
                    return cached
            if not parts:
                key = f"{prefix}/report.md"
                try:
                    parts.append(await self._services.storage.get_text(key))
                except Exception:
                    logger.warning("Could not read research report from %s", key)
                    return ""
            text = "\n\n".join(parts)
            self._stage_outputs[stage] = text
            return text

        cached = self._stage_outputs.get(stage)
        if cached is not None:
            return cached

        if stage == Stage.FORMALIZE:
            parts: list[str] = []
            for slug in self.state.approved_paradigms:
                key = f"{prefix}/formulations/{slug}.md"
                try:
                    parts.append(await self._services.storage.get_text(key))
                except Exception:
                    logger.warning("Could not read formulation %s", key)
            text = "\n\n".join(parts)
            self._stage_outputs[stage] = text
            return text

        if stage == Stage.REASON:
            parts = []
            scope = self.state.approved_specs or self.state.selected_formulations
            for paradigm, fids in scope.items():
                for fid in fids:
                    key = f"{models}/reasoner/{paradigm}/{fid}.json"
                    try:
                        parts.append(await self._services.storage.get_text(key))
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
                        model_text = await self._services.storage.get_text(model_key)
                        parts.append(
                            "\n".join(
                                [
                                    "## Builder artifact",
                                    f"Paradigm: {paradigm}",
                                    f"Formulation: {fid}",
                                    f"S3 key: {model_key}",
                                    "",
                                    model_text,
                                ]
                            )
                        )
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
            Stage.CLASSIFY_UMBRELLA: self._classify_umbrella,
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
        trace_tokens = agrex_context.bind(self._tracer, self.emit)
        try:
            await self._run_loop(handlers)
        finally:
            agrex_context.reset(trace_tokens)
            await self._finalize_trace(self.state.run_id)

    async def _run_loop(self, handlers: dict) -> None:
        # Emit agent list so the frontend knows which agents are available
        await self._emit_agents()

        import os

        from decisionlab.eval.timing import record_stage

        max_retries = int(
            os.environ.get("DECISIONLAB_MAX_STAGE_RETRIES", _MAX_STAGE_RETRIES)
        )
        retries_at_stage: dict[Stage, int] = {}

        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]
            _set_recording_stage(current_stage)

            if current_stage in _TIMELINE_WORK_STAGES:
                self._tracer.stage(current_stage.value)
                await self._send_event(self._tracer.events()[-1])
            elif current_stage in _REVIEW_STAGES:
                # The review stage's value is already "review_<work>" (e.g. "review_research"),
                # which is exactly the marker kind we want.
                self._tracer.marker(current_stage.value, color="#fbbf24")
                await self._send_event(self._tracer.events()[-1])
                review_id = self._trace_id("human_review", current_stage.value)
                parent = {
                    Stage.REVIEW_RESEARCH: "researcher",
                    Stage.REVIEW_FORMALIZE: "formalizer",
                    Stage.REVIEW_REASON: "reasoner",
                    Stage.REVIEW_BUILD: "builder",
                }[current_stage]
                await self._trace_node_once(
                    "tool",
                    review_id,
                    current_stage.value,
                    parent=parent,
                    status="running",
                    metadata={"hitl": True, "stage": current_stage.value},
                )

            async with record_stage(current_stage.value):
                await handler()

            if current_stage in _REVIEW_STAGES:
                review_id = self._trace_id("human_review", current_stage.value)
                self._tracer.done(
                    review_id, metadata={"endedAt": agrex_context.now_ms()}
                )
                await self._trace_last()

            # Stuck-stage detection: work-stage handlers swallow agent failures
            # and return without advancing `state.stage`. Without this, a
            # persistently-failing agent loops forever in non-interactive runs.
            if self.state.stage == current_stage:
                retries_at_stage[current_stage] = (
                    retries_at_stage.get(current_stage, 0) + 1
                )
                if retries_at_stage[current_stage] >= max_retries:
                    raise RuntimeError(
                        f"Pipeline stuck at {current_stage.value}: "
                        f"{max_retries} consecutive failed attempts. Aborting "
                        f"to prevent infinite loop."
                    )
            else:
                retries_at_stage.clear()

            # `--until X` enforcement: when the user just finished reviewing the
            # stop_after stage, terminate cleanly. Consolidation + finalization
            # still run via the block below.
            if (
                self._stop_after_review is not None
                and current_stage == self._stop_after_review
            ):
                memory_stage = {
                    review: memory for memory, review in _REVIEW_STAGE_OF_MEMORY.items()
                }.get(current_stage)
                if self.memory_agent is None or self.state.stage != memory_stage:
                    self.state.stage = Stage.DONE
            elif self._stop_after_review is not None:
                memory_stage = {
                    review: memory for memory, review in _REVIEW_STAGE_OF_MEMORY.items()
                }.get(self._stop_after_review)
                if current_stage == memory_stage:
                    self.state.stage = Stage.DONE

            await self.state.save(self._services)
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

    async def _classify_umbrella(self) -> None:
        """Pre-anchor the run to a canonical paradigm umbrella.

        Runs one Haiku call against the canonical-paradigms fixture. The
        result is stored on ``state.umbrella`` (in-memory only) and passed
        to ``Researcher.run`` so the final emission collapses variant
        slugs into the umbrella's slug. Failure here degrades to
        ``state.umbrella=None`` and the Researcher behaves as it did
        pre-classifier — never aborts the run.
        """
        from decisionlab.agents.classifier import classify_umbrella

        try:
            from decisionlab.knowledge.seed import _load_fixture

            known = _load_fixture()
        except Exception as exc:
            logger.warning("Classifier: cannot load canonical paradigms — %s", exc)
            self.state.umbrella = None
            self.state.stage = Stage.RESEARCH
            return

        try:
            decision = await classify_umbrella(
                self.state.problem,
                client=self.client,
                known_umbrellas=known,
            )
        except Exception as exc:
            logger.warning("Classifier failed (%s) — proceeding without anchor", exc)
            self.state.umbrella = None
            self.state.stage = Stage.RESEARCH
            return

        self.state.umbrella = decision
        self.console.print(
            f"[dim]Anchored to: {decision.chosen_slug} "
            f"(confidence={decision.confidence:.2f})[/dim]"
        )
        self.state.stage = Stage.RESEARCH

    async def _do_research(self) -> None:
        from decisionlab.agents.researcher import Researcher

        self.console.print("[bold]Running Researcher...[/bold]")
        self._tracer.agent(
            "researcher",
            "Researcher",
            metadata={"startedAt": agrex_context.now_ms()},
        )
        await self._send_event(self._tracer.events()[-1])
        try:
            r = Researcher(
                client=self.client,
                search=self.search,
                storage=self._services.storage,
                db=self._services.db,
                run_id=self.state.run_id,
                kg=self._services.kg,
                vectors=self._services.vectors,
                embeddings=self._services.embeddings,
                **self._knowledge_tool_kwargs("researcher"),
            )
            report = await r.run(
                self.state.problem,
                anchor_umbrella=self.state.umbrella,  # type: ignore[arg-type]
            )
        except Exception as exc:
            self.console.print(f"[bold red]Researcher failed: {exc}[/bold red]")
            logger.exception("Researcher failed")
            self._tracer.error(
                "researcher",
                error=exc,
                metadata={
                    "endedAt": agrex_context.now_ms(),
                    "error_type": type(exc).__name__,
                },
            )
            await self._send_event(self._tracer.events()[-1])
            return  # stay at current stage
        # Cache the in-memory text so the Memory Agent doesn't round-trip S3.
        self._stage_outputs[Stage.RESEARCH] = report.summary
        await self._trace_research_artifacts()
        self._tracer.done("researcher", metadata={"endedAt": agrex_context.now_ms()})
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.RESEARCH)

    async def _review_research(self) -> None:
        from decisionlab.agents.deep_researcher import DeepResearcher

        while True:
            approved, additional = await self.feedback.review_research(
                self.state.reports_dir,
                run_id=self.state.run_id,
            )
            if additional:
                self.console.print(
                    f"[bold]Running DeepResearcher for '{additional}'...[/bold]"
                )
                try:
                    dr = DeepResearcher(
                        client=self.client,
                        search=self.search,
                        storage=self._services.storage,
                        db=self._services.db,
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
            for slug in approved:
                paradigm_id = self._trace_id("paradigm", slug)
                await self._trace_node_once(
                    "artifact",
                    paradigm_id,
                    slug,
                    parent="researcher",
                    status="done",
                    metadata={"artifact_type": "approved_paradigm", "slug": slug},
                )
                await self._trace_edge_once(
                    "researcher", paradigm_id, edge_type="approves", label="approves"
                )
            await self.state.save(self._services)
            break
        self.state.stage = self._next_after_review(Stage.REVIEW_RESEARCH)

    async def _do_formalize(self) -> None:
        from decisionlab.agents.formalizer import Formalizer

        self.console.print("[bold]Running Formalizer...[/bold]")
        self._tracer.agent(
            "formalizer",
            "Formalizer",
            parent="researcher",
            metadata={"startedAt": agrex_context.now_ms()},
        )
        await self._send_event(self._tracer.events()[-1])
        try:
            f = Formalizer(
                client=self.client,
                research_prefix=self.state.research_prefix,
                storage=self._services.storage,
                db=self._services.db,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("formalizer"),
            )
            await f.run(self.state.approved_paradigms)
        except Exception as exc:
            self.console.print(f"[bold red]Formalizer failed: {exc}[/bold red]")
            logger.exception("Formalizer failed")
            self._tracer.error(
                "formalizer",
                error=exc,
                metadata={
                    "endedAt": agrex_context.now_ms(),
                    "error_type": type(exc).__name__,
                },
            )
            await self._send_event(self._tracer.events()[-1])
            return
        await self._trace_formalization_artifacts()
        self._tracer.done("formalizer", metadata={"endedAt": agrex_context.now_ms()})
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.FORMALIZE)

    async def _review_formalize(self) -> None:
        selected = await self.feedback.review_formalize(
            self.state.reports_dir,
            self.state.approved_paradigms,
            run_id=self.state.run_id,
        )
        self.state.selected_formulations = await _convert_formulations_to_slugs(
            self.state,
            selected,
            self._services,
        )
        await self._trace_selected_formulations()
        await self.state.save(self._services)
        from decisionlab.tools.reports import generate_tree_map

        await generate_tree_map(self.state, self._services)
        self.state.stage = self._next_after_review(Stage.REVIEW_FORMALIZE)

    async def _get_env_spec(self) -> None:
        try:
            src_path = await self.feedback.get_env_spec()
            # Upload env_spec to S3
            env_spec_data = src_path.read_text()
            s3_key = f"research/{self.state.run_id}/env_spec.json"
            await self._services.storage.put_text(s3_key, env_spec_data)
            self.state.env_spec_path = Path(s3_key)  # transitional
            await self._trace_node_once(
                "tool",
                "env_spec_input",
                "Environment spec input",
                parent="formalizer",
                status="done",
                metadata={"hitl": True, "s3_key": s3_key},
            )
            await self._trace_file_artifact(
                s3_key, parent="env_spec_input", artifact_type="env_spec"
            )
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
        self._tracer.agent(
            "reasoner",
            "Reasoner",
            parent="formalizer",
            metadata={"startedAt": agrex_context.now_ms()},
        )
        await self._send_event(self._tracer.events()[-1])
        try:
            r = Reasoner(
                client=self.client,
                research_prefix=self.state.research_prefix,
                models_prefix=self.state.models_prefix,
                storage=self._services.storage,
                db=self._services.db,
                run_id=self.state.run_id,
                **self._knowledge_tool_kwargs("reasoner"),
            )
            await r.run(selected)
            await self._validate_reasoner_files(selected)
        except Exception as exc:
            self.console.print(f"[bold red]Reasoner failed: {exc}[/bold red]")
            logger.exception("Reasoner failed")
            self._tracer.error(
                "reasoner",
                error=exc,
                metadata={
                    "endedAt": agrex_context.now_ms(),
                    "error_type": type(exc).__name__,
                },
            )
            await self._send_event(self._tracer.events()[-1])
            return
        await self._trace_reasoner_artifacts()
        self._tracer.done("reasoner", metadata={"endedAt": agrex_context.now_ms()})
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.REASON)

    async def _review_reason(self) -> None:
        from decisionlab.agents.reasoner import Reasoner

        while True:
            approved, rejections, formalizer_reruns = await self.feedback.review_reason(
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
                for paradigm, fids in self.state.approved_specs.items():
                    for fid in fids:
                        spec_id = self._trace_id("approved_spec", paradigm, fid)
                        await self._trace_node_once(
                            "artifact",
                            spec_id,
                            fid,
                            parent=self._trace_id("reasoner", paradigm, fid),
                            status="done",
                            metadata={
                                "artifact_type": "approved_spec",
                                "paradigm": paradigm,
                                "formulation": fid,
                            },
                        )
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
        self.state.stage = self._next_after_review(Stage.REVIEW_REASON)

    async def _do_build(self) -> None:
        from decisionlab.agents.builder import Builder

        n_specs = sum(len(fs) for fs in self.state.approved_specs.values())
        self.console.print(f"[bold]Running Builder for {n_specs} spec(s)...[/bold]")
        self._tracer.agent(
            "builder",
            "Builder",
            parent="reasoner",
            metadata={"startedAt": agrex_context.now_ms()},
        )
        await self._send_event(self._tracer.events()[-1])
        try:
            b = Builder(
                client=self.client,
                models_prefix=self.state.models_prefix,
                storage=self._services.storage,
                db=self._services.db,
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
            self._tracer.error(
                "builder",
                error=exc,
                metadata={
                    "endedAt": agrex_context.now_ms(),
                    "error_type": type(exc).__name__,
                },
            )
            await self._send_event(self._tracer.events()[-1])
            return
        await self._trace_builder_artifacts()
        self._tracer.done("builder", metadata={"endedAt": agrex_context.now_ms()})
        await self._send_event(self._tracer.events()[-1])
        self.state.stage = self._next_after_work(Stage.BUILD)

    async def _review_build(self) -> None:
        from decisionlab.agents.builder import Builder

        while True:
            _approved, rejections, reasoner_reruns = await self.feedback.review_build(
                self.state.reports_dir,
                self.state.build_results,
            )
            if not rejections and not reasoner_reruns:
                await self._register_approved_models()
                self.state.stage = self._next_after_review(Stage.REVIEW_BUILD)
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        await self._services.storage.delete(
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
                        storage=self._services.storage,
                        db=self._services.db,
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
        """Verify expected reasoner files exist; rename mismatches; rewrite
        any ``formulation_id`` field that drifted from the canonical slug.

        Phase E enforces that the spec's ``formulation_id`` always matches
        the filename slug. The pre-rewrite Reasoner sometimes emitted
        ``"formulation_id": "Q-Learning_TD"`` while the file was saved as
        ``q-learning-td.json`` — downstream consumers (Builder, KG writer,
        memory namespace) ended up with two different identifiers for the
        same artifact.
        """
        prefix = f"{self.state.models_prefix}/reasoner/"
        for paradigm, formulations in selected.items():
            for formulation in formulations:
                expected = f"{prefix}{paradigm}/{formulation}.json"
                if not await self._services.storage.exists(expected):
                    paradigm_prefix = f"{prefix}{paradigm}/"
                    keys = await self._services.storage.list(paradigm_prefix)
                    json_keys = [k for k in keys if k.endswith(".json")]
                    if json_keys:
                        old_key = json_keys[0]
                        await self._services.storage.rename(old_key, expected)
                        logger.warning(
                            "Reasoner file renamed: %s → %s",
                            old_key,
                            expected,
                        )
                    else:
                        logger.warning("Reasoner file missing: %s", expected)
                        continue

                # Re-pin formulation_id to the canonical slug.
                try:
                    text = await self._services.storage.get_text(expected)
                    data = json.loads(text)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("formulation_id") == formulation:
                    continue
                logger.warning(
                    "Reasoner: rewriting formulation_id %r → %r in %s",
                    data.get("formulation_id"),
                    formulation,
                    expected,
                )
                data["formulation_id"] = formulation
                await self._services.storage.put_text(
                    expected, json.dumps(data, indent=2)
                )

    async def _validate_builder_files(
        self,
        approved_specs: dict[str, list[str]],
    ) -> None:
        """Verify expected builder files exist; rename mismatches."""
        prefix = f"{self.state.models_prefix}/builder/"
        for paradigm, formulations in approved_specs.items():
            for formulation in formulations:
                expected = f"{prefix}{paradigm}/{formulation}_model.py"
                if await self._services.storage.exists(expected):
                    continue
                paradigm_prefix = f"{prefix}{paradigm}/"
                keys = await self._services.storage.list(paradigm_prefix)
                model_keys = [k for k in keys if k.endswith("_model.py")]
                if model_keys:
                    old_key = model_keys[0]
                    await self._services.storage.rename(old_key, expected)
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

        from decisionlab.agents.builder_sub import derive_class_name
        from shared.models import Model

        run_uuid = uuid.UUID(self.state.run_id)

        async with self._services.db.get_session() as session:
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

                    # Phase E: class_name is derived from formulation slug,
                    # not extracted from source. This locks the registry to
                    # the same identifier the Builder was instructed to use.
                    # We still touch S3 to confirm the model file exists —
                    # registering a row pointing at a missing artifact
                    # would mislead downstream consumers.
                    try:
                        await self._services.storage.get_text(s3_model_key)
                    except Exception:
                        logger.warning(
                            "Model file not found in S3: %s — skipping registration",
                            s3_model_key,
                        )
                        continue
                    class_name = derive_class_name(formulation)

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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
                        storage=self._services.storage,
                        db=self._services.db,
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
