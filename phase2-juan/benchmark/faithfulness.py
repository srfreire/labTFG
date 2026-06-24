"""Reporter faithfulness check (Layer 3, light).

The Reporter turns simulation data into a prose/PDF report. Its specific risk is
*hallucination*: stating numbers that do not match the simulation. This module
implements a QAGS-style numeric consistency check (Wang, Cho & Lewis, 2020):
each key magnitude is a "question"; the answer derived from the source (the
simulation ground truth) must match the answer the report gives for the same
magnitude. It is pure code — no LLM, no NLI model — so it runs in the fast suite
and is fully reproducible.

A magnitude is:
    - ``faithful``     the report mentions it and states the true value
                       (within tolerance),
    - ``hallucinated`` the report mentions it but states a different value,
    - ``missing``      the report does not mention it.

The faithfulness score is ``faithful / (faithful + hallucinated)`` — missing
magnitudes do not count against faithfulness, only against coverage.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

_NUMBER = re.compile(r"-?\d[\d.,]*")
# Split into clauses on sentence punctuation and on clause-separating commas —
# but NOT on commas used as a decimal separator inside a number (e.g. "6,0"),
# so each magnitude's number is not contaminated by a neighbouring magnitude's.
_SENTENCE_SPLIT = re.compile(r"[.;\n]|,(?!\s*\d)")


@dataclass
class Magnitude:
    """One checkable quantity: its true value and the words that announce it."""

    key: str
    value: float
    keywords: tuple[str, ...]


@dataclass
class MagnitudeResult:
    key: str
    status: str  # "faithful" | "hallucinated" | "missing"
    true_value: float
    claimed: list[float] = field(default_factory=list)


@dataclass
class FaithfulnessReport:
    results: list[MagnitudeResult]

    @property
    def score(self) -> float:
        checked = [r for r in self.results if r.status != "missing"]
        if not checked:
            return 1.0
        faithful = sum(1 for r in checked if r.status == "faithful")
        return faithful / len(checked)

    @property
    def hallucinations(self) -> list[MagnitudeResult]:
        return [r for r in self.results if r.status == "hallucinated"]


def _parse_number(token: str) -> float | None:
    """Parse a numeric token, tolerating thousands/decimal separators."""
    t = token.rstrip(".,")
    # A lone comma with a non-3-digit tail ("6,0") is a decimal separator; every
    # other comma is digit grouping and gets stripped.
    if t.count(",") == 1 and "." not in t and len(t.split(",")[1]) != 3:
        t = t.replace(",", ".")
    else:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _numbers_near(text: str, keywords: Sequence[str]) -> list[float]:
    """All numbers appearing in sentences that mention any keyword."""
    found: list[float] = []
    low = text.lower()
    for raw_sentence in _SENTENCE_SPLIT.split(low):
        if any(k in raw_sentence for k in keywords):
            for tok in _NUMBER.findall(raw_sentence):
                n = _parse_number(tok)
                if n is not None:
                    found.append(n)
    return found


def _matches(
    value: float, candidates: Sequence[float], *, rel_tol: float, abs_tol: float
) -> bool:
    return any(
        math.isclose(value, c, rel_tol=rel_tol, abs_tol=abs_tol) for c in candidates
    )


def check_report(
    report_text: str,
    magnitudes: Sequence[Magnitude],
    *,
    rel_tol: float = 0.001,
    abs_tol: float = 0.5,
) -> FaithfulnessReport:
    """Score a report's numeric faithfulness against known ground-truth values."""
    results: list[MagnitudeResult] = []
    for m in magnitudes:
        claimed = _numbers_near(report_text, m.keywords)
        if not claimed:
            status = "missing"
        elif _matches(m.value, claimed, rel_tol=rel_tol, abs_tol=abs_tol):
            status = "faithful"
        else:
            status = "hallucinated"
        results.append(
            MagnitudeResult(
                key=m.key, status=status, true_value=m.value, claimed=claimed
            )
        )
    return FaithfulnessReport(results)


# Markers planted by the Reporter's standard-PDF fallback path
# (simlab.reporter): a degraded report carries this banner instead of the real
# tectonic-compiled content.
_FALLBACK_MARKERS = (
    "aviso de compilación",
    "formato estándar con el contenido del informe",
    "no se pudo ejecutar tectonic",
    "la compilación latex detallada no se pudo completar",
)


def is_fallback_report(text: str) -> bool:
    """True if ``text`` is the Reporter's standard-PDF fallback, not the real one.

    A fallback report is a degraded artefact (the LaTeX compile failed); its
    numbers may be correct but it is not the intended output. Faithfulness of a
    fallback report is meaningless, so callers should gate on this first.
    """
    low = text.lower()
    return any(marker in low for marker in _FALLBACK_MARKERS)


def ground_truth_from_records(records: Sequence) -> list[Magnitude]:
    """Derive the canonical checkable magnitudes from a simulation rollout.

    Mirrors the magnitudes the chapter calls out: food consumed, number of
    steps, total reward, and (when the model exposes it) final energy.
    """
    food_eaten = sum(1 for r in records if r.action == "eat" and r.reward > 0)
    total_reward = sum(r.reward for r in records)
    steps = len(records)
    mags = [
        Magnitude(
            "comida_consumida",
            float(food_eaten),
            ("comida", "comió", "alimento", "ingesta", "food", "consum"),
        ),
        Magnitude("pasos", float(steps), ("paso", "step", "iteracion", "iteración")),
        Magnitude(
            "recompensa_total",
            float(total_reward),
            ("recompensa", "reward", "retorno"),
        ),
    ]
    last = records[-1].state if records else {}
    if "energy_reserves" in last:
        mags.append(
            Magnitude(
                "energia_final",
                round(float(last["energy_reserves"]), 1),
                ("energía", "energia", "energy", "reserva"),
            )
        )
    return mags
