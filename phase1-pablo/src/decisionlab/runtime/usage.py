"""Per-run token usage accounting.

Records every Anthropic API response's ``usage`` block, grouped by model.
Call :func:`record` after each ``messages.create()``; call :func:`log_summary`
at the end of a CLI command to show cumulative usage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Any

from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


def _as_int(value: Any) -> int:
    """Coerce API-usage fields to int; drop anything non-numeric (e.g. test mocks)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


@dataclass
class _ModelTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    calls: int = 0


@dataclass
class _Meter:
    totals: dict[str, _ModelTotals] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def record(self, model: str, usage: Any) -> None:
        if usage is None:
            return
        data = usage_as_dict(usage)
        input_tokens = data["input_tokens"]
        output_tokens = data["output_tokens"]
        cache_creation = data["cache_creation_input_tokens"]
        cache_read = data["cache_read_input_tokens"]
        with self.lock:
            totals = self.totals.setdefault(model, _ModelTotals())
            totals.input_tokens += input_tokens
            totals.output_tokens += output_tokens
            totals.cache_creation_input_tokens += cache_creation
            totals.cache_read_input_tokens += cache_read
            totals.calls += 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self.lock:
            return {
                model: {
                    "input_tokens": t.input_tokens,
                    "output_tokens": t.output_tokens,
                    "cache_creation_input_tokens": t.cache_creation_input_tokens,
                    "cache_read_input_tokens": t.cache_read_input_tokens,
                    "calls": t.calls,
                }
                for model, t in self.totals.items()
            }

    def reset(self) -> None:
        with self.lock:
            self.totals.clear()


_METER = _Meter()


@dataclass
class _Counters:
    values: dict[str, int] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def increment(self, name: str, by: int = 1) -> None:
        with self.lock:
            self.values[name] = self.values.get(name, 0) + by

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return dict(self.values)

    def reset(self) -> None:
        with self.lock:
            self.values.clear()


_COUNTERS = _Counters()


def record(model: str, usage: Any) -> None:
    _METER.record(model, usage)
    if usage is None:
        return
    data = usage_as_dict(usage)
    tokens = total_tokens(data)
    cost = estimate_usage_usd(model, data)
    try:
        from decisionlab.runtime import agrex_context

        agrex_context.record_llm_usage(
            model,
            data,
            tokens=tokens,
            cost=cost,
        )
    except Exception:
        logger.debug("Could not attach LLM usage to agrex trace", exc_info=True)


def snapshot() -> dict[str, dict[str, int]]:
    return _METER.snapshot()


def usage_as_dict(usage: Any) -> dict[str, int]:
    """Return the Anthropic usage fields this project accounts for."""
    return {
        "input_tokens": _as_int(getattr(usage, "input_tokens", 0)),
        "output_tokens": _as_int(getattr(usage, "output_tokens", 0)),
        "cache_creation_input_tokens": _as_int(
            getattr(usage, "cache_creation_input_tokens", 0)
        ),
        "cache_read_input_tokens": _as_int(
            getattr(usage, "cache_read_input_tokens", 0)
        ),
    }


def total_tokens(usage: dict[str, int]) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def estimate_usage_usd(model: str, usage: dict[str, int]) -> float:
    """Estimate cost for one model usage record using the eval rates table."""
    from decisionlab.eval.cost import estimate_usd

    return estimate_usd({model: usage})


def reset() -> None:
    _METER.reset()
    _COUNTERS.reset()


def increment_counter(name: str, by: int = 1) -> None:
    """Bump a named scalar counter (e.g. ``ner.skipped`` / ``ner.evaluated``).

    Used to record skip-vs-evaluate decisions in the retrieve pipeline
    without conflating them with the per-model token totals tracked by
    :func:`record`.
    """
    _COUNTERS.increment(name, by)


def counters_snapshot() -> dict[str, int]:
    return _COUNTERS.snapshot()


def log_summary(console: Console | None = None) -> None:
    """Render a token-usage summary. Uses a rich table if a Console is given, else logger."""
    data = snapshot()
    if not data:
        return

    totals_in = sum(v["input_tokens"] for v in data.values())
    totals_out = sum(v["output_tokens"] for v in data.values())
    totals_cache_c = sum(v["cache_creation_input_tokens"] for v in data.values())
    totals_cache_r = sum(v["cache_read_input_tokens"] for v in data.values())
    totals_calls = sum(v["calls"] for v in data.values())

    if console is not None:
        table = Table(title="Token usage", show_footer=True)
        table.add_column("Model", footer="TOTAL")
        table.add_column("Calls", justify="right", footer=str(totals_calls))
        table.add_column("Input", justify="right", footer=f"{totals_in:,}")
        table.add_column("Output", justify="right", footer=f"{totals_out:,}")
        table.add_column(
            "Cache (create)", justify="right", footer=f"{totals_cache_c:,}"
        )
        table.add_column("Cache (read)", justify="right", footer=f"{totals_cache_r:,}")
        for model, t in sorted(data.items()):
            table.add_row(
                model,
                str(t["calls"]),
                f"{t['input_tokens']:,}",
                f"{t['output_tokens']:,}",
                f"{t['cache_creation_input_tokens']:,}",
                f"{t['cache_read_input_tokens']:,}",
            )
        console.print(table)
        return

    logger.info(
        "Token usage — calls=%d input=%d output=%d cache_create=%d cache_read=%d",
        totals_calls,
        totals_in,
        totals_out,
        totals_cache_c,
        totals_cache_r,
    )
    for model, t in sorted(data.items()):
        logger.info(
            "  %s — calls=%d input=%d output=%d",
            model,
            t["calls"],
            t["input_tokens"],
            t["output_tokens"],
        )
