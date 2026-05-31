"""Context-local Agrex tracing for agent-loop internals.

The Router owns the actual ``agrex.Tracer`` instance. Runtime helpers use this
module to add tool nodes from deep inside ``dispatch_tools`` without threading
trace parameters through every agent constructor.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

EmitFn = Callable[[dict], Awaitable[None]]

_TRACER_VAR: ContextVar[Any | None] = ContextVar(
    "decisionlab_agrex_tracer", default=None
)
_EMIT_VAR: ContextVar[EmitFn | None] = ContextVar(
    "decisionlab_agrex_emit", default=None
)
_PARENT_VAR: ContextVar[str | None] = ContextVar(
    "decisionlab_agrex_parent", default=None
)


_STAGE_PARENT = {
    "research": "researcher",
    "formalize": "formalizer",
    "reason": "reasoner",
    "build": "builder",
    "memory_research": "memory_agent:researcher",
    "memory_formalize": "memory_agent:formalizer",
    "memory_reason": "memory_agent:reasoner",
    "memory_build": "memory_agent:builder",
}


def bind(tracer: Any, emit: EmitFn | None) -> tuple:
    """Bind a tracer + optional emitter to the current async context."""
    return (_TRACER_VAR.set(tracer), _EMIT_VAR.set(emit))


def reset(tokens: tuple) -> None:
    """Undo ``bind``."""
    tracer_token, emit_token = tokens
    _TRACER_VAR.reset(tracer_token)
    _EMIT_VAR.reset(emit_token)


def set_parent(parent: str | None):
    """Temporarily override the parent used for tool nodes."""
    return _PARENT_VAR.set(parent)


def reset_parent(token) -> None:
    _PARENT_VAR.reset(token)


async def _emit_last_event(tracer: Any) -> None:
    emit = _EMIT_VAR.get()
    if emit is None:
        return
    events = tracer.events()
    if events:
        await emit(events[-1])


def _default_parent() -> str | None:
    from decisionlab.runtime.tool_calls import current_stage

    return _STAGE_PARENT.get(current_stage())


async def trace_tool_start(name: str, args: object) -> str | None:
    """Add a running tool node and return its node id."""
    tracer = _TRACER_VAR.get()
    if tracer is None:
        return None
    parent = _PARENT_VAR.get() or _default_parent()
    node_id = f"tool:{name}:{uuid.uuid4().hex[:8]}"
    metadata: dict[str, Any] = {}
    if isinstance(args, dict):
        for key in ("path", "paradigm", "query", "namespace", "top_k"):
            if key in args:
                metadata[key] = args[key]
    tracer.tool(node_id, name, parent=parent, args=args, metadata=metadata or None)
    await _emit_last_event(tracer)
    return node_id


async def trace_tool_done(
    node_id: str | None, *, succeeded: bool, error: str | None = None
) -> None:
    """Mark a traced tool node done/failed."""
    if node_id is None:
        return
    tracer = _TRACER_VAR.get()
    if tracer is None:
        return
    if succeeded:
        tracer.done(node_id)
    else:
        tracer.error(node_id, error=error)
    await _emit_last_event(tracer)
