"""Per-run tool-call ledger for the eval harness.

Captures every tool invocation made through ``dispatch_tools`` so eval
predicates can assert on what the agent loop actually did (e.g.
``tool_called(retrieve_knowledge, min=1)``). The router sets the current
work stage; the dispatcher records ``ToolCall`` entries; the runner
collects the list at end-of-run and stitches it onto the ``PipelineRunResult``.

Implementation: two ``ContextVar``s. The list is opt-in — when no list is
set (e.g. the interactive CLI), recording is a no-op so production paths
pay nothing. The Stage enum import is deferred to the ``stage`` property
to avoid a router→runtime→router import cycle.
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decisionlab.router import Stage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    name: str
    stage: str  # Stage.value (or "unknown" before any handler sets it)
    args_hash: str
    succeeded: bool
    # Optional structured payload. Default ``None`` for ordinary dispatcher
    # entries (no behaviour change). Used by ``record_loop_cap_reached`` to
    # carry diagnostic context (topic excerpt + last tool uses + log length)
    # without growing a sibling ledger or mutating ``PipelineRunResult``'s
    # JSON contract.
    details: dict | None = None
    # Wall time spent inside the dispatcher handler. None for legacy
    # call sites that don't measure (interactive CLI, tests).
    duration_ms: float | None = None


# Sentinel ``name`` for synthetic ``ToolCall`` entries written by
# ``record_loop_cap_reached``. Picked to be impossible to collide with a
# real tool name and to remain inert against the ``tool_called(name)`` eval
# predicate (which matches by exact name).
LOOP_CAP_REACHED_NAME = "__loop_cap_reached__"


_TOOL_CALLS_VAR: ContextVar[list[ToolCall] | None] = ContextVar(
    "decisionlab_tool_calls", default=None
)
_STAGE_VAR: ContextVar[str] = ContextVar("decisionlab_current_stage", default="unknown")


def start_recording() -> list[ToolCall]:
    """Begin a fresh recording session and return the collecting list.

    The eval runner calls this before ``router.run()`` and reads the
    populated list afterwards. Idempotent across runs because each call
    binds a new list to the context var.
    """
    log: list[ToolCall] = []
    _TOOL_CALLS_VAR.set(log)
    return log


def set_stage(stage: Stage | str) -> None:
    """Bind the stage label that will be tagged onto subsequent tool calls.

    Accepts ``Stage`` (uses ``.value``) or a raw string. The router calls
    this once per loop iteration before dispatching the handler.
    """
    value = getattr(stage, "value", None)
    if not isinstance(value, str):
        value = str(stage)
    _STAGE_VAR.set(value)


def current_stage() -> str:
    """Return the stage label bound to the current context."""
    return _STAGE_VAR.get()


def record(
    name: str,
    args: object,
    succeeded: bool,
    *,
    duration_ms: float | None = None,
) -> None:
    """Append a ``ToolCall`` to the active recording list, if any.

    No-ops silently when no recording session is active (the interactive
    CLI never starts one). ``args`` is hashed rather than stored to keep
    the in-memory log lightweight and PII-free.
    """
    log = _TOOL_CALLS_VAR.get()
    if log is None:
        return
    try:
        blob = json.dumps(args, sort_keys=True, default=str).encode()
    except (TypeError, ValueError):
        blob = repr(args).encode()
    args_hash = hashlib.md5(blob, usedforsecurity=False).hexdigest()[:12]
    log.append(
        ToolCall(
            name=name,
            stage=_STAGE_VAR.get(),
            args_hash=args_hash,
            succeeded=succeeded,
            duration_ms=duration_ms,
        )
    )


def record_loop_cap_reached(
    *,
    topic_excerpt: str,
    last_tool_uses: list[list[dict]],
    max_iterations: int,
) -> None:
    """Append a synthetic ``ToolCall`` marking the agent loop's max-iteration exit.

    Phase F validation observed 4/12 topics hitting the cap without an
    ``end_turn`` — well above the < 5% target. The cause isn't obvious
    from stderr alone (the ``Loop iteration N/7 — calling ...`` log line
    is too coarse), so we capture *what* the model was still trying to do
    at the cap as a structured trace event.

    ``tool_call_log_length`` is captured *before* the synthetic entry is
    appended, so it counts only real dispatcher tool calls preceding the
    cap. Implemented as a ``ToolCall`` with ``name=LOOP_CAP_REACHED_NAME``
    so the existing ledger/serialization plumbing carries it for free;
    the ``tool_called`` eval predicate matches by exact name and so
    doesn't accidentally count cap-hits as legitimate tool invocations.
    """
    log = _TOOL_CALLS_VAR.get()
    if log is None:
        return
    log.append(
        ToolCall(
            name=LOOP_CAP_REACHED_NAME,
            stage=_STAGE_VAR.get(),
            args_hash="",
            succeeded=False,
            details={
                "topic_excerpt": topic_excerpt,
                "last_tool_uses": last_tool_uses,
                "tool_call_log_length": len(log),
                "max_iterations": max_iterations,
            },
        )
    )
