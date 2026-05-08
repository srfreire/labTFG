"""Timing collector for the eval harness.

Mirrors the ContextVar pattern used by ``runtime.tool_calls`` so the
runner can opt into recording per-stage durations without changing
non-eval code paths.

Per-tool durations are *not* stored separately — they come along on
``ToolCall.duration_ms`` (Task 2). ``TimingLog.summarize_tool_calls``
aggregates those into p50/p95/avg by tool name.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from statistics import mean

from decisionlab.runtime.tool_calls import ToolCall


@dataclass(frozen=True)
class StageTiming:
    stage: str
    duration_ms: float
    failed: bool


@dataclass
class TimingLog:
    stages: list[StageTiming] = field(default_factory=list)

    @staticmethod
    def summarize_tool_calls(
        calls: Iterable[ToolCall],
    ) -> dict[str, dict[str, float]]:
        """Compute calls / p50 / p95 / avg per tool name. Skips entries
        with ``duration_ms is None``."""
        buckets: dict[str, list[float]] = {}
        for c in calls:
            if c.duration_ms is None:
                continue
            buckets.setdefault(c.name, []).append(c.duration_ms)
        out: dict[str, dict[str, float]] = {}
        for name, durations in buckets.items():
            durations.sort()
            n = len(durations)
            p50 = durations[n // 2] if n else 0.0
            p95_idx = max(0, min(n - 1, round(0.95 * n) - 1))
            p95 = durations[p95_idx] if n else 0.0
            out[name] = {
                "calls": float(n),
                "p50_ms": float(p50),
                "p95_ms": float(p95),
                "avg_ms": float(mean(durations)),
            }
        return out


_TIMING_VAR: ContextVar[TimingLog | None] = ContextVar(
    "decisionlab_eval_timing", default=None
)


def start_timing() -> TimingLog:
    """Bind a fresh TimingLog to the current context. Idempotent across
    runs because each call replaces the binding."""
    log = TimingLog()
    _TIMING_VAR.set(log)
    return log


def current_timing() -> TimingLog | None:
    return _TIMING_VAR.get()


@asynccontextmanager
async def record_stage(name: str):
    """Async context manager: record duration of a stage body. No-op
    when no TimingLog is bound (production / interactive CLI)."""
    log = _TIMING_VAR.get()
    if log is None:
        yield
        return
    t0 = time.monotonic_ns()
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        elapsed_ms = (time.monotonic_ns() - t0) / 1_000_000
        log.stages.append(
            StageTiming(stage=name, duration_ms=elapsed_ms, failed=failed)
        )
