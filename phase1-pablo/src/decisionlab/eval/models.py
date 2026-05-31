"""Frozen result types for the eval harness.

Kept separate from runner.py so the suite/assertions/report layers can
import these without pulling in the runner's heavy deps (Anthropic SDK,
shared infra).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from decisionlab.eval.timing import TimingLog
from decisionlab.router import Stage
from decisionlab.runtime.tool_calls import ToolCall


@dataclass(frozen=True)
class PipelineRunResult:
    """Outcome of one ``run_pipeline`` invocation.

    All collection fields default to empty so partial-failure cases
    (e.g. RESEARCH succeeded, FORMALIZE crashed) still yield a usable
    result rather than blowing up the suite.

    Note: ``stages_run`` is the *requested* prefix of stages, not the
    stages that actually completed. Use ``failed_at`` to see where the
    pipeline stopped — if it's None, every stage in ``stages_run``
    completed successfully.
    """

    run_id: str
    topic: str
    stages_run: tuple[Stage, ...]
    paradigms: tuple[str, ...] = ()
    formulations: tuple[str, ...] = ()
    reasoner_specs: tuple[str, ...] = ()
    builder_artifacts: tuple[Path, ...] = ()
    memory_per_stage: dict[str, dict] = field(default_factory=dict)
    usage: dict[str, dict[str, int]] = field(default_factory=dict)
    duration_ms: int = 0
    failed_at: Stage | None = None
    error: str | None = None
    tool_call_log: tuple[ToolCall, ...] = ()
    # ISO-8601 wall-clock timestamp when the pipeline started — needed by
    # ``paradigm_reused`` to distinguish "this run minted the node" from
    # "this run hit an existing node".
    started_at: str = ""
    # Snapshot of Paradigm.slug -> created_at taken immediately before the
    # router starts. KG assertions can use this if the live graph changes
    # before assertion evaluation.
    preexisting_paradigms: dict[str, str] = field(default_factory=dict)
    # Per-stage durations captured by ``eval.timing.record_stage`` while the
    # router was running. ``None`` for legacy callers that construct a
    # ``PipelineRunResult`` without going through ``run_pipeline``.
    timing: TimingLog | None = None

    @property
    def succeeded(self) -> bool:
        return self.failed_at is None

    def total_nodes_created(self) -> int:
        """Sum of ``nodes_created`` across every memory stage in this run."""
        return sum(p.get("nodes_created", 0) for p in self.memory_per_stage.values())

    def total_relations_created(self) -> int:
        return sum(
            p.get("relations_created", 0) for p in self.memory_per_stage.values()
        )
