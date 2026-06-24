"""Token/latency metering wrapper for the Anthropic/OpenRouter client.

The simlab agents share one ``anthropic.AsyncAnthropic`` client and nothing in
the codebase records ``response.usage``. This thin proxy wraps the client so the
benchmark e2e runner can report real token counts, an estimated cost and
per-stage latency without touching agent code: it intercepts ``messages.create``,
sums usage, and otherwise delegates to the real client.

Cost is an *estimate* from the published per-million-token prices below; token
counts are exact (from the provider's ``usage``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Approximate USD per 1M tokens (input, output). Used only for an estimate; the
# token counts reported alongside are the hard numbers.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "claude-opus": (15.0, 75.0),
}


def _price_for(model: str) -> tuple[float, float]:
    for key, price in _PRICES.items():
        if key in model:
            return price
    return (3.0, 15.0)  # default to sonnet-class


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    seconds: float = 0.0
    by_model: dict[str, tuple[int, int]] = field(default_factory=dict)

    def cost_usd(self) -> float:
        total = 0.0
        for model, (inp, out) in self.by_model.items():
            pin, pout = _price_for(model)
            total += inp / 1e6 * pin + out / 1e6 * pout
        return round(total, 4)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "calls": self.calls,
            "seconds": round(self.seconds, 2),
            "estimated_cost_usd": self.cost_usd(),
        }


class _MeteredMessages:
    def __init__(self, inner, usage: Usage) -> None:
        self._inner = inner
        self._usage = usage

    async def create(self, **kwargs):
        model = kwargs.get("model", "")
        t0 = time.perf_counter()
        response = await self._inner.create(**kwargs)
        self._usage.seconds += time.perf_counter() - t0
        self._usage.calls += 1
        u = getattr(response, "usage", None)
        if u is not None:
            # Include cache read/creation so the input count is realistic under
            # prompt caching (plain input_tokens excludes cached prefixes).
            inp = (
                (getattr(u, "input_tokens", 0) or 0)
                + (getattr(u, "cache_read_input_tokens", 0) or 0)
                + (getattr(u, "cache_creation_input_tokens", 0) or 0)
            )
            out = getattr(u, "output_tokens", 0) or 0
            self._usage.input_tokens += inp
            self._usage.output_tokens += out
            prev_in, prev_out = self._usage.by_model.get(model, (0, 0))
            self._usage.by_model[model] = (prev_in + inp, prev_out + out)
        return response


class MeteredClient:
    """Wraps an AsyncAnthropic client, accumulating usage on ``.usage``."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.usage = Usage()
        self.messages = _MeteredMessages(inner.messages, self.usage)

    def __getattr__(self, name):
        # Delegate everything else (e.g. .beta, .with_options) to the real client.
        return getattr(self._inner, name)
