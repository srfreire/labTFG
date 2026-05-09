"""Run a single topic through the pipeline non-interactively.

Glue between the eval harness and the existing ``Router`` + ``MemoryAgent``
infrastructure. Uses ``AutoApproveFeedback`` so REVIEW_* stages don't block
on human input.

The runner does **not** call ``init_services`` / ``shutdown_services`` —
that lifecycle belongs to the suite (or the eval CLI command). This keeps
the runner cheap to call repeatedly inside one process.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.timing import start_timing
from decisionlab.feedback_port import AutoApproveFeedback
from decisionlab.router import PipelineState, Router, Stage
from decisionlab.runtime import usage as usage_module
from decisionlab.runtime.tool_calls import start_recording as _start_tool_call_recording
from decisionlab.tools.reports import slugify

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

    from decisionlab.domain.ports import WebSearchPort
    from shared.services import Services

logger = logging.getLogger(__name__)

# Canonical work-stage order — `stages` arg must be a contiguous prefix.
_STAGE_ORDER: tuple[Stage, ...] = (
    Stage.RESEARCH,
    Stage.FORMALIZE,
    Stage.REASON,
    Stage.BUILD,
)


def _validate_stages(stages: Iterable[Stage]) -> tuple[Stage, ...]:
    """Return the contiguous prefix of ``_STAGE_ORDER`` matching *stages*.

    The eval harness only supports running a prefix because every stage
    depends on its predecessor's artifacts. ``{FORMALIZE}`` alone is
    nonsensical — there'd be no paradigms to formalize.

    An empty iterable is allowed and yields an empty tuple — used by
    offline suites that run only ``suite_assertions:`` without any
    pipeline work.
    """
    requested = set(stages)
    if not requested:
        return ()
    bad = requested - set(_STAGE_ORDER)
    if bad:
        raise ValueError(
            f"unsupported stages {sorted(s.value for s in bad)}; "
            f"valid: {[s.value for s in _STAGE_ORDER]}"
        )
    # Highest-indexed requested stage defines the prefix length.
    last_idx = max(_STAGE_ORDER.index(s) for s in requested)
    prefix = _STAGE_ORDER[: last_idx + 1]
    missing_in_prefix = set(prefix) - requested
    if missing_in_prefix:
        # Caller asked for {RESEARCH, REASON} or similar — fill in the gap
        # so they get the artifacts they need. We log this rather than
        # raise because "I want REASON" implicitly needs RESEARCH first
        # and forcing the user to spell out the prefix is friction.
        logger.info(
            "Filling stage gaps: requested %s, running %s",
            sorted(s.value for s in requested),
            [s.value for s in prefix],
        )
    return prefix


def _topic_to_reports_dir(topic: str, run_id: str, base: Path) -> Path:
    slug_words = slugify(topic).split("-")[:5]
    slug = "-".join(slug_words) or "topic"
    out = base / f"{date.today().isoformat()}-{slug}-{run_id[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    return out


async def _create_run_row(run_id: str, topic: str, services: Services) -> None:
    """Insert the Run row that the Router expects to update mid-pipeline.

    Mirrors what ``cli.run`` and ``server.run_pipeline`` do at startup —
    the Router writes ``status``, ``memory_results``, ``s3_report_key`` to
    this row as the run progresses. Without this row those updates would
    silently no-op (router catches the missing-row case).

    Eval runs are tagged ``kind='eval'`` so the retention prune command can
    reap them by age (memory-refactor P3-003 / phase-3 R3). Interactive
    runs created via ``cli.run`` and ``server.run_pipeline`` keep the
    ``kind='prod'`` default.
    """
    from shared.models import Run

    if services.db is None:
        logger.debug("services.db is None — skipping Run-row insert (degraded mode)")
        return
    async with services.db.get_session() as session:
        session.add(
            Run(
                id=uuid.UUID(run_id),
                problem_description=topic,
                status="running",
                s3_prefix=f"research/{run_id}",
                kind="eval",
            )
        )
        await session.commit()


async def run_pipeline(
    topic: str,
    *,
    services: Services,
    stages: Iterable[Stage] = (Stage.RESEARCH,),
    env_spec_path: Path | None = None,
    project_root: Path,
    client: AsyncAnthropic,
    search: WebSearchPort,
    reports_root: Path = Path("evals/runs"),
    run_id: str | None = None,
    reset_usage: bool = True,
) -> PipelineRunResult:
    """Drive one topic through a contiguous prefix of pipeline stages.

    Args:
        topic: Free-text problem description for the Researcher.
        stages: Iterable of ``Stage`` — auto-filled to a prefix of
            [RESEARCH, FORMALIZE, REASON, BUILD]. Defaults to research-only.
        env_spec_path: Required iff ``REASON`` or ``BUILD`` is in the prefix.
            ``AutoApproveFeedback.get_env_spec`` returns this when the
            pipeline reaches GET_ENV_SPEC.
        project_root: Where the Builder writes ``*_model.py`` files. Use a
            per-topic directory to keep eval runs isolated.
        client: An initialised Anthropic client.
        search: Web-search adapter (DuckDuckGoAdapter is the default in
            the rest of the codebase).
        reports_root: Local dir for the pipeline's ``reports_dir`` —
            defaults to ``evals/runs`` so eval artifacts stay segregated
            from interactive runs.
        run_id: Optional pre-generated UUID4. One is created when omitted.
        reset_usage: When True, clears the global usage meter before the
            run so the returned ``usage`` is per-run rather than cumulative
            across the process.

    Returns:
        ``PipelineRunResult`` with per-stage artifacts and KG counts.
        On partial failure the result still returns; ``failed_at`` and
        ``error`` describe where it stopped.
    """
    stages_run = _validate_stages(stages)
    needs_env = Stage.REASON in stages_run or Stage.BUILD in stages_run
    if needs_env and env_spec_path is None:
        raise ValueError(
            "env_spec_path is required when stages include REASON or BUILD"
        )

    rid = run_id or str(uuid.uuid4())

    if reset_usage:
        usage_module.reset()

    started_at_iso = datetime.now(UTC).isoformat()
    tool_call_log = _start_tool_call_recording()
    timing_log = start_timing()

    # Offline suite path: no stages requested means skip the entire
    # pipeline — useful for ``suite_assertions:``-only suites that
    # operate over a fixture rather than running the agent pipeline.
    if not stages_run:
        return PipelineRunResult(
            run_id=rid,
            topic=topic,
            stages_run=(),
            started_at=started_at_iso,
            tool_call_log=tuple(tool_call_log),
            timing=timing_log,
        )

    reports_dir = _topic_to_reports_dir(topic, rid, reports_root)
    await _create_run_row(rid, topic, services)

    state = PipelineState(
        stage=Stage.CLASSIFY_UMBRELLA,
        problem=topic,
        reports_dir=reports_dir,
        run_id=rid,
    )
    feedback = AutoApproveFeedback(env_spec_path=env_spec_path)
    stop_after = stages_run[-1]

    router = Router(
        client=client,
        state=state,
        search=search,
        project_root=project_root,
        services=services,
        stop_after=stop_after,
        feedback=feedback,
    )

    t0 = time.monotonic()
    failed_at: Stage | None = None
    error: str | None = None
    try:
        await router.run()
    except Exception as exc:
        logger.exception(
            "run_pipeline crashed at stage=%s for topic=%r", state.stage, topic
        )
        failed_at = state.stage
        error = str(exc)
    duration_ms = int((time.monotonic() - t0) * 1000)

    # If router exited cleanly but didn't hit DONE, the run was cut short —
    # locate the work-stage where it stopped (skip MEMORY_/REVIEW_ as those
    # don't represent a "stage at which the pipeline is stuck").
    if failed_at is None and state.stage != Stage.DONE:
        failed_at = state.stage
        error = f"pipeline terminated early at {state.stage.value}"

    paradigms = tuple(state.approved_paradigms)
    formulations = tuple(
        slug for slug, fids in state.selected_formulations.items() if fids
    )
    reasoner_specs = tuple(
        fid for fids in state.selected_formulations.values() for fid in fids
    )
    builder_artifacts = tuple(
        project_root / f"{rid}-{paradigm}-{fid}-model.py"
        for paradigm, fids in state.approved_specs.items()
        for fid in fids
    )

    return PipelineRunResult(
        run_id=rid,
        topic=topic,
        stages_run=stages_run,
        paradigms=paradigms,
        formulations=formulations,
        reasoner_specs=reasoner_specs,
        builder_artifacts=builder_artifacts,
        memory_per_stage=dict(router.memory_results),
        usage=usage_module.snapshot(),
        duration_ms=duration_ms,
        failed_at=failed_at,
        error=error,
        tool_call_log=tuple(tool_call_log),
        started_at=started_at_iso,
        timing=timing_log,
    )
