"""Pipeline orchestration and human feedback routing."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable

from anthropic import AsyncAnthropic
from rich.console import Console

from decisionlab.domain.models import RerunRequest
from decisionlab.domain.ports import WebSearchPort

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


# ---------------------------------------------------------------------------
# PipelineState
# ---------------------------------------------------------------------------

_STATE_FILENAME = "pipeline_state.json"
_FORMULATION_HEADER_RE = re.compile(
    r"^##\s+Formulation\s+(\d+)\s*:\s*(.+)$", re.MULTILINE,
)


@dataclass
class PipelineState:
    stage: Stage
    problem: str
    reports_dir: Path

    # Filled progressively
    approved_paradigms: list[str] = field(default_factory=list)
    selected_formulations: dict[str, list[str]] = field(default_factory=dict)
    env_spec_path: Path | None = None
    approved_specs: list[str] = field(default_factory=list)
    build_results: dict[str, str] = field(default_factory=dict)
    pending_reruns: list[RerunRequest] = field(default_factory=list)

    # ID registry (T-P-F hierarchy)
    topic_id: str = "T01"
    id_registry: dict[str, str] = field(default_factory=dict)
    _paradigm_counter: int = 0
    _formulation_counters: dict[str, int] = field(default_factory=dict)

    # -- ID assignment -------------------------------------------------------

    def assign_paradigm_id(self, slug: str) -> str:
        """Assign ``T01-P{NN}`` to a paradigm slug. Idempotent for same slug."""
        existing = self.id_registry.get(slug)
        if existing is not None:
            return existing
        self._paradigm_counter += 1
        pid = f"{self.topic_id}-P{self._paradigm_counter:02d}"
        self.id_registry[slug] = pid
        return pid

    def assign_formulation_id(self, paradigm_slug: str, formulation_name: str) -> str:
        """Assign ``T01-P{NN}-F{NN}`` to a formulation. Idempotent for same name+paradigm."""
        key = f"{paradigm_slug}::{formulation_name}"
        existing = self.id_registry.get(key)
        if existing is not None:
            return existing
        paradigm_id = self.id_registry.get(paradigm_slug)
        if paradigm_id is None:
            raise ValueError(
                f"Paradigm '{paradigm_slug}' not in registry. "
                "Call assign_paradigm_id first."
            )
        count = self._formulation_counters.get(paradigm_id, 0) + 1
        self._formulation_counters[paradigm_id] = count
        fid = f"{paradigm_id}-F{count:02d}"
        self.id_registry[key] = fid
        return fid

    def get_id(self, slug: str) -> str | None:
        """Look up ID by slug. Returns ``None`` if not registered."""
        return self.id_registry.get(slug)

    def get_slug(self, registry_id: str) -> str | None:
        """Reverse look up slug by ID. Returns ``None`` if not found."""
        for slug, rid in self.id_registry.items():
            if rid == registry_id:
                return slug
        return None

    # -- persistence ---------------------------------------------------------

    def save(self) -> None:
        """Atomic write to ``reports_dir/pipeline_state.json``."""
        data = {
            "stage": self.stage.value,
            "problem": self.problem,
            "reports_dir": str(self.reports_dir),
            "approved_paradigms": self.approved_paradigms,
            "selected_formulations": self.selected_formulations,
            "env_spec_path": str(self.env_spec_path) if self.env_spec_path else None,
            "approved_specs": self.approved_specs,
            "build_results": self.build_results,
            "pending_reruns": [
                {"target": r.target, "paradigm": r.paradigm, "feedback": r.feedback}
                for r in self.pending_reruns
            ],
            "topic_id": self.topic_id,
            "id_registry": self.id_registry,
            "paradigm_counter": self._paradigm_counter,
            "formulation_counters": self._formulation_counters,
        }
        dest = self.reports_dir / _STATE_FILENAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.reports_dir, suffix=".tmp", prefix=".state_"
        )
        try:
            with open(fd, "w") as fh:
                json.dump(data, fh, indent=2)
            Path(tmp_path).replace(dest)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        logger.debug("PipelineState saved to %s", dest)

    @classmethod
    def load(cls, reports_dir: Path) -> PipelineState:
        """Load state from ``reports_dir/pipeline_state.json``."""
        state_file = reports_dir / _STATE_FILENAME
        try:
            raw = state_file.read_text()
            data = json.loads(raw)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Pipeline state not found at {state_file}. "
                "Start a new run or check the reports directory."
            ) from None
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Corrupt pipeline state at {state_file}: {exc}"
            ) from exc

        env_path = data.get("env_spec_path")
        return cls(
            stage=Stage(data["stage"]),
            problem=data["problem"],
            reports_dir=Path(data["reports_dir"]),
            approved_paradigms=data.get("approved_paradigms", []),
            selected_formulations=data.get("selected_formulations", {}),
            env_spec_path=Path(env_path) if env_path else None,
            approved_specs=data.get("approved_specs", []),
            build_results=data.get("build_results", {}),
            pending_reruns=[
                RerunRequest(target=r["target"], paradigm=r["paradigm"], feedback=r["feedback"])
                for r in data.get("pending_reruns", [])
            ],
            topic_id=data.get("topic_id", "T01"),
            id_registry=data.get("id_registry", {}),
            _paradigm_counter=data.get("paradigm_counter", 0),
            _formulation_counters=data.get("formulation_counters", {}),
        )


def _convert_formulations_to_ids(
    state: PipelineState,
    raw_selected: dict[str, list[int]],
) -> dict[str, list[str]]:
    """Convert ``{slug: [int]}`` from feedback to ``{slug: [registry_id]}``."""
    converted: dict[str, list[str]] = {}
    for slug, kept_numbers in raw_selected.items():
        if not kept_numbers:
            converted[slug] = []
            continue
        md_path = state.reports_dir / "formulations" / f"{slug}.md"
        if not md_path.exists():
            logger.warning("Formulation file not found for '%s'; skipping", slug)
            converted[slug] = []
            continue
        text = md_path.read_text()
        num_to_name = {
            int(m.group(1)): m.group(2).strip()
            for m in _FORMULATION_HEADER_RE.finditer(text)
        }
        ids: list[str] = []
        for num in kept_numbers:
            name = num_to_name.get(num)
            if name is None:
                logger.warning("Formulation %d not found in %s.md", num, slug)
                continue
            fid = state.assign_formulation_id(slug, name)
            ids.append(fid)
        converted[slug] = ids
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

    async def _emit(self, msg: dict) -> None:
        """Send an event to the frontend (no-op in CLI mode)."""
        if self.emit is not None:
            await self.emit(msg)

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
        while self.state.stage != Stage.DONE:
            current_stage = self.state.stage  # capture before handler
            handler = handlers[current_stage]
            await self._emit({
                "type": "stage_change",
                "stage": current_stage.value,
                "status": "running",
            })
            await handler()
            await self._emit({
                "type": "stage_change",
                "stage": current_stage.value,
                "status": "done",
            })
            self.state.save()

    # -- stage handlers ------------------------------------------------------

    async def _do_research(self) -> None:
        from decisionlab.agents.researcher import Researcher

        self.console.print("[bold]Running Researcher...[/bold]")
        await self._emit({"type": "node_add", "node": {"id": "researcher", "kind": "agent", "label": "Researcher", "status": "running"}})
        try:
            r = Researcher(
                client=self.client,
                search=self.search,
                reports_dir=self.state.reports_dir,
            )
            await r.run(self.state.problem)
        except Exception as exc:
            self.console.print(f"[bold red]Researcher failed: {exc}[/bold red]")
            logger.exception("Researcher failed")
            await self._emit({"type": "node_update", "id": "researcher", "status": "error"})
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
                    self.state.reports_dir, self.emit,
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
                        reports_dir=self.state.reports_dir,
                    )
                    await dr.run(additional)
                except Exception as exc:
                    self.console.print(
                        f"[bold red]DeepResearcher failed for '{additional}': {exc}[/bold red]"
                    )
                    logger.exception("DeepResearcher failed for %s", additional)
                # Loop back to let user review again
                continue
            # No more additions — store approved and assign IDs
            self.state.approved_paradigms = approved
            for slug in approved:
                self.state.assign_paradigm_id(slug)
            self.state.save()
            break
        self.state.stage = Stage.FORMALIZE

    async def _do_formalize(self) -> None:
        from decisionlab.agents.formalizer import Formalizer

        self.console.print("[bold]Running Formalizer...[/bold]")
        await self._emit({"type": "node_add", "node": {"id": "formalizer", "kind": "agent", "label": "Formalizer", "status": "running"}})
        await self._emit({"type": "edge_add", "edge": {"source": "researcher", "target": "formalizer"}})
        try:
            f = Formalizer(
                client=self.client,
                reports_dir=self.state.reports_dir,
            )
            await f.run(self.state.approved_paradigms)
        except Exception as exc:
            self.console.print(f"[bold red]Formalizer failed: {exc}[/bold red]")
            logger.exception("Formalizer failed")
            await self._emit({"type": "node_update", "id": "formalizer", "status": "error"})
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
            )
        else:
            from decisionlab.feedback import review_formalize
            selected = await review_formalize(
                self.state.reports_dir,
                self.state.approved_paradigms,
            )
        self.state.selected_formulations = _convert_formulations_to_ids(
            self.state, selected,
        )
        self.state.save()
        self.state.stage = Stage.GET_ENV_SPEC

    async def _get_env_spec(self) -> None:
        try:
            if self._web_mode:
                from decisionlab.web_feedback import get_env_spec
                assert self.emit is not None
                src_path = await get_env_spec(self.emit)
            else:
                from decisionlab.feedback import get_env_spec
                src_path = await get_env_spec()
            dest = self.state.reports_dir / "env_spec.json"
            shutil.copy2(src_path, dest)
            self.state.env_spec_path = dest
        except Exception as exc:
            self.console.print(f"[bold red]env_spec setup failed: {exc}[/bold red]")
            logger.exception("env_spec setup failed")
            return
        self.state.stage = Stage.REASON

    async def _do_reason(self) -> None:
        from decisionlab.agents.reasoner import Reasoner

        paradigms = list(self.state.approved_paradigms)
        self.console.print(
            f"[bold]Running Reasoner for {len(paradigms)} paradigm(s)...[/bold]"
        )
        await self._emit({"type": "node_add", "node": {"id": "reasoner", "kind": "agent", "label": "Reasoner", "status": "running"}})
        await self._emit({"type": "edge_add", "edge": {"source": "formalizer", "target": "reasoner"}})
        try:
            r = Reasoner(
                client=self.client,
                reports_dir=self.state.reports_dir,
            )
            await r.run(paradigms)
        except Exception as exc:
            self.console.print(f"[bold red]Reasoner failed: {exc}[/bold red]")
            logger.exception("Reasoner failed")
            await self._emit({"type": "node_update", "id": "reasoner", "status": "error"})
            return
        await self._emit({"type": "node_update", "id": "reasoner", "status": "done"})
        self.state.stage = Stage.REVIEW_REASON

    async def _review_reason(self) -> None:
        from decisionlab.agents.reasoner import Reasoner

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_reason
                assert self.emit is not None
                approved, rejections = await review_reason(
                    self.state.reports_dir, self.emit,
                )
            else:
                from decisionlab.feedback import review_reason
                approved, rejections = await review_reason(
                    self.state.reports_dir,
                )
            if not rejections:
                self.state.approved_specs = approved
                break
            # Re-run Reasoner for each rejected paradigm
            for _, paradigm_slug, _ in rejections:
                self.console.print(
                    f"[bold]Re-running Reasoner for '{paradigm_slug}'...[/bold]"
                )
                try:
                    r = Reasoner(
                        client=self.client,
                        reports_dir=self.state.reports_dir,
                    )
                    await r.run([paradigm_slug])
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

        paradigms = list(self.state.approved_paradigms)
        self.console.print(
            f"[bold]Running Builder for {len(paradigms)} paradigm(s)...[/bold]"
        )
        await self._emit({"type": "node_add", "node": {"id": "builder", "kind": "agent", "label": "Builder", "status": "running"}})
        await self._emit({"type": "edge_add", "edge": {"source": "reasoner", "target": "builder"}})
        try:
            b = Builder(
                client=self.client,
                reports_dir=self.state.reports_dir,
                project_root=self.project_root,
            )
            report = await b.run(paradigms)
            self.state.build_results = report.results
        except Exception as exc:
            self.console.print(f"[bold red]Builder failed: {exc}[/bold red]")
            logger.exception("Builder failed")
            await self._emit({"type": "node_update", "id": "builder", "status": "error"})
            return
        await self._emit({"type": "node_update", "id": "builder", "status": "done"})
        self.state.stage = Stage.REVIEW_BUILD

    async def _review_build(self) -> None:
        from decisionlab.routing_llm import classify_feedback

        build_results = self.state.build_results

        while True:
            if self._web_mode:
                from decisionlab.web_feedback import review_build
                assert self.emit is not None
                user_feedback = await review_build(build_results, self.emit)
            else:
                from decisionlab.feedback import review_build
                user_feedback = await review_build(build_results)
            if user_feedback is None:
                self.state.stage = Stage.DONE
                return

            # Classify the feedback to determine re-run target
            self.console.print("[bold]Classifying feedback...[/bold]")
            try:
                rerun = await classify_feedback(
                    client=self.client,
                    feedback=user_feedback,
                    paradigms=self.state.approved_paradigms,
                    build_output="\n\n".join(
                        f"--- {slug} ---\n{content}"
                        for slug, content in build_results.items()
                    ) or None,
                )
            except Exception as exc:
                self.console.print(
                    f"[bold red]Feedback classification failed: {exc}[/bold red]"
                )
                logger.exception("classify_feedback failed")
                continue

            self.console.print(
                f"[bold yellow]Re-run target:[/bold yellow] {rerun.target} "
                f"for paradigm '{rerun.paradigm}'"
            )

            # Confirm with user
            if self._web_mode:
                # In web mode, the user already confirmed via the review panel
                confirmed = True
            else:
                import questionary
                confirmed = await asyncio.to_thread(
                    questionary.confirm(
                        f"Re-run from {rerun.target} for '{rerun.paradigm}'?",
                        default=True,
                    ).unsafe_ask,
                )
            if not confirmed:
                self.console.print("[dim]Re-run cancelled. Returning to review.[/dim]")
                continue

            # Execute re-run cascade
            await self._emit({"type": "rerun", "target": rerun.target, "paradigm": rerun.paradigm})
            await self._emit({"type": "graph_clear", "from_stage": rerun.target})
            await self._execute_rerun_cascade(rerun)
            # Loop back to REVIEW_BUILD with fresh build results

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
                        reports_dir=self.state.reports_dir,
                    )
                    await dr.run(paradigm)

                elif stage_name == "formalizer":
                    from decisionlab.agents.formalizer import Formalizer

                    self.console.print(
                        f"[bold]Cascade: Formalizer for '{paradigm}'...[/bold]"
                    )
                    f = Formalizer(
                        client=self.client,
                        reports_dir=self.state.reports_dir,
                    )
                    await f.run([paradigm])

                elif stage_name == "reasoner":
                    from decisionlab.agents.reasoner import Reasoner

                    self.console.print(
                        f"[bold]Cascade: Reasoner for '{paradigm}'...[/bold]"
                    )
                    r = Reasoner(
                        client=self.client,
                        reports_dir=self.state.reports_dir,
                    )
                    await r.run([paradigm])

                elif stage_name == "builder":
                    from decisionlab.agents.builder import Builder

                    self.console.print(
                        f"[bold]Cascade: Builder for '{paradigm}'...[/bold]"
                    )
                    b = Builder(
                        client=self.client,
                        reports_dir=self.state.reports_dir,
                        project_root=self.project_root,
                    )
                    report = await b.run([paradigm])
                    self.state.build_results = report.results

            except Exception as exc:
                self.console.print(
                    f"[bold red]Cascade: {stage_name} failed for '{paradigm}': {exc}[/bold red]"
                )
                logger.exception("Cascade %s failed for %s", stage_name, paradigm)
                return  # abort cascade on failure
