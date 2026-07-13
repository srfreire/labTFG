"""Context-local Agrex tracing for agent-loop internals.

The Router owns the actual ``agrex.Tracer`` instance. Runtime helpers use this
module to add tool nodes from deep inside ``dispatch_tools`` without threading
trace parameters through every agent constructor.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from copy import deepcopy
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
_USAGE_BY_NODE_VAR: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "decisionlab_agrex_usage_by_node", default=None
)

_SUPPRESSED_TOOL_NODES = {"launch_deep_research"}


_STAGE_PARENT = {
    "research": "researcher",
    "review_research": "researcher",
    "formalize": "formalizer",
    "reason": "reasoner",
    "review_reason": "reasoner",
    "build": "builder",
    "memory_research": "memory_agent:researcher",
    "memory_formalize": "memory_agent:formalizer",
    "memory_reason": "memory_agent:reasoner",
    "memory_build": "memory_agent:builder",
}


def trace_id(*parts: object) -> str:
    """Match the router's stable Agrex id convention."""
    raw = ":".join(str(p) for p in parts if p is not None and str(p) != "")
    return raw.replace("/", ":").replace(" ", "-")


def bind(tracer: Any, emit: EmitFn | None) -> tuple:
    """Bind a tracer + optional emitter to the current async context."""
    return (
        _TRACER_VAR.set(tracer),
        _EMIT_VAR.set(emit),
        _USAGE_BY_NODE_VAR.set({}),
    )


def reset(tokens: tuple) -> None:
    """Undo ``bind``."""
    tracer_token, emit_token, usage_token = tokens
    _TRACER_VAR.reset(tracer_token)
    _EMIT_VAR.reset(emit_token)
    _USAGE_BY_NODE_VAR.reset(usage_token)


def set_parent(parent: str | None):
    """Temporarily override the parent used for tool nodes."""
    return _PARENT_VAR.set(parent)


def reset_parent(token) -> None:
    _PARENT_VAR.reset(token)


def _tracer_has_node(tracer: Any, node_id: str) -> bool:
    return any(
        event.get("type") == "node_add"
        and isinstance(event.get("node"), dict)
        and event["node"].get("id") == node_id
        for event in tracer.events()
    )


def _tracer_has_edge(tracer: Any, edge_id: str) -> bool:
    return any(
        event.get("type") == "edge_add"
        and isinstance(event.get("edge"), dict)
        and event["edge"].get("id") == edge_id
        for event in tracer.events()
    )


async def trace_sub_agent_start(
    node_id: str,
    label: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record a sub-agent before its first tool call.

    Deep researchers run inside the Researcher's tool loop. Recording their
    node at launch time keeps the persisted trace causal: the child tools have
    a visible parent before they are emitted.
    """
    tracer = _TRACER_VAR.get()
    if tracer is None or _tracer_has_node(tracer, node_id):
        return

    parent = _current_parent()
    node_metadata = dict(metadata or {})
    node_metadata.setdefault("startedAt", now_ms())
    tracer.sub_agent(
        node_id,
        label,
        parent=parent,
        status="running",
        metadata=node_metadata,
    )
    await _emit_last_event(tracer)

    if parent:
        edge_id = trace_id("edge", parent, "launches", node_id)
        if not _tracer_has_edge(tracer, edge_id):
            tracer.edge(
                id=edge_id,
                source=parent,
                target=node_id,
                type="launches",
                label="launches",
            )
            await _emit_last_event(tracer)


async def trace_sub_agent_done(
    node_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Mark a traced sub-agent complete after its work and report save."""
    tracer = _TRACER_VAR.get()
    if tracer is None or not _tracer_has_node(tracer, node_id):
        return
    tracer.done(node_id, metadata=metadata)
    await _emit_last_event(tracer)


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


def now_ms() -> int:
    """Milliseconds since epoch, matching agrex trace timestamps."""
    return int(time.time() * 1000)


def _current_parent() -> str | None:
    return _PARENT_VAR.get() or _default_parent()


async def trace_tool_start(name: str, args: object) -> str | None:
    """Add a running tool node and return its node id."""
    if name in _SUPPRESSED_TOOL_NODES:
        return None
    tracer = _TRACER_VAR.get()
    if tracer is None:
        return None
    parent = _current_parent()
    node_id = f"tool:{name}:{uuid.uuid4().hex[:8]}"
    metadata: dict[str, Any] = {
        "startedAt": now_ms(),
        "tool_name": name,
    }
    if isinstance(args, dict):
        for key in ("path", "paradigm", "query", "namespace", "top_k"):
            if key in args:
                metadata[key] = args[key]
    tracer.tool(node_id, name, parent=parent, args=args, metadata=metadata or None)
    await _emit_last_event(tracer)
    return node_id


async def trace_tool_done(
    node_id: str | None,
    *,
    succeeded: bool,
    error: Any | None = None,
    output: Any | None = None,
    duration_ms: float | None = None,
) -> None:
    """Mark a traced tool node done/failed."""
    if node_id is None:
        return
    tracer = _TRACER_VAR.get()
    if tracer is None:
        return
    metadata: dict[str, Any] = {"endedAt": now_ms()}
    if duration_ms is not None:
        metadata["duration_ms"] = duration_ms
    if succeeded:
        if output is not None:
            text = str(output)
            metadata["result_chars"] = len(text)
            metadata["output"] = text[:2000] + ("..." if len(text) > 2000 else "")
        tracer.done(node_id, metadata=metadata)
    else:
        if isinstance(error, BaseException):
            metadata["error_type"] = type(error).__name__
        error_message = str(error) if error is not None else "Tool failed"
        metadata["error_message"] = error_message
        tracer.error(
            node_id,
            error=error if error is not None else error_message,
            metadata=metadata,
        )
    await _emit_last_event(tracer)


def record_llm_usage(
    model: str,
    usage: dict[str, int],
    *,
    tokens: int,
    cost: float,
) -> None:
    """Attach cumulative LLM usage to the current agrex parent node.

    The persisted trace is the source of truth for replay, so this synchronous
    path intentionally writes directly to the tracer. Live WS emission is left
    to surrounding awaited trace events; past-run replay will always include
    these metadata-only updates.
    """
    tracer = _TRACER_VAR.get()
    node_id = _current_parent()
    if tracer is None or node_id is None:
        return

    usage_by_node = _USAGE_BY_NODE_VAR.get()
    if usage_by_node is None:
        usage_by_node = {}
        _USAGE_BY_NODE_VAR.set(usage_by_node)

    aggregate = usage_by_node.setdefault(
        node_id,
        {
            "tokens": 0,
            "cost": 0.0,
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "models": {},
        },
    )
    aggregate["tokens"] += tokens
    aggregate["cost"] += cost
    aggregate["llm_calls"] += 1

    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        aggregate[key] += usage.get(key, 0)

    models = aggregate["models"]
    per_model = models.setdefault(
        model,
        {
            "calls": 0,
            "tokens": 0,
            "cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    )
    per_model["calls"] += 1
    per_model["tokens"] += tokens
    per_model["cost"] += cost
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        per_model[key] += usage.get(key, 0)

    tracer.update(
        node_id,
        metadata={
            "tokens": aggregate["tokens"],
            "cost": round(aggregate["cost"], 8),
            "llm_calls": aggregate["llm_calls"],
            "input_tokens": aggregate["input_tokens"],
            "output_tokens": aggregate["output_tokens"],
            "cache_creation_input_tokens": aggregate["cache_creation_input_tokens"],
            "cache_read_input_tokens": aggregate["cache_read_input_tokens"],
            "last_model": model,
            "models": deepcopy(models),
        },
    )
