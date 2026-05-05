"""Cost estimation from a usage snapshot.

Used by the suite runner's budget watchdog to decide when to hard-kill
a run. Rates are baseline Anthropic public pricing in USD per million
tokens — adjust via ``MODEL_RATES`` if your billing differs (e.g. via
OpenRouter routing markup).

Returning a single USD float lets the watchdog compare against the
suite's ``budget.max_usd_total``.
"""

from __future__ import annotations

# USD per 1M tokens. Source: anthropic.com/pricing as of 2026-01.
# Override at process start by mutating MODEL_RATES if you're routing
# through a markup provider.
MODEL_RATES: dict[str, dict[str, float]] = {
    # Claude Opus 4.x family
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "anthropic/claude-opus-4.6": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "anthropic/claude-opus-4.7": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    # Claude Sonnet 4.x family
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "anthropic/claude-sonnet-4.6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    # Claude Haiku 4.x family
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1},
    "anthropic/claude-haiku-4.5": {"input": 1.0, "output": 5.0, "cache_read": 0.1},
}

# Fallback rate for unknown models — pessimistic so under-pricing is unlikely.
_FALLBACK = {"input": 15.0, "output": 75.0, "cache_read": 1.5}


def estimate_usd(usage: dict[str, dict[str, int]]) -> float:
    """Convert a ``usage_module.snapshot()`` payload into total USD spent.

    Cache-creation tokens are billed at the input rate (1.0×); cache reads
    at the cache_read rate (0.1× of input for Sonnet/Haiku, 0.1× for Opus).
    Output tokens at the output rate.

    Unknown models log no warning — they use ``_FALLBACK`` rates so the
    watchdog stays conservative rather than silently undercounting.
    """
    total = 0.0
    for model, totals in usage.items():
        rates = MODEL_RATES.get(model, _FALLBACK)
        in_tok = totals.get("input_tokens", 0)
        out_tok = totals.get("output_tokens", 0)
        cache_create = totals.get("cache_creation_input_tokens", 0)
        cache_read = totals.get("cache_read_input_tokens", 0)
        total += in_tok * rates["input"] / 1_000_000
        total += cache_create * rates["input"] / 1_000_000
        total += out_tok * rates["output"] / 1_000_000
        total += cache_read * rates["cache_read"] / 1_000_000
    return total
