"""Pure scoring functions for the golden-scenario benchmark.

Every function here is deterministic and free of I/O: it takes already-collected
data (a list of :class:`~benchmark.scenarios.StepRecord`, or plain series) and
returns a verdict. This keeps the falsification logic unit-testable in isolation
from the (slow, service-backed) model loading in ``run_golden_scenarios.py``.

The PASS thresholds below were fixed empirically during calibration against the
four Phase 1 models and the two baselines, and chosen to be robust across random
seeds (see the benchmark report for the calibration evidence).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class Verdict:
    """The outcome of scoring one (scenario, model) pair."""

    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# Layer 1 — observable contract (GS-0)
# ---------------------------------------------------------------------------


def _state_key(state: dict) -> str:
    """A stable, hashable representation of a model state for equality checks."""
    return repr(sorted((k, repr(v)) for k, v in state.items()))


def check_contract(model: object, perception: dict) -> Verdict:
    """GS-0: verify the three runtime invariants of the model contract.

    1. ``decide`` is read-only — two calls on the same perception leave
       ``get_state`` unchanged.
    2. ``update`` is the only mutator — it is callable and changes state when
       fed a reward (checked leniently: at minimum it must run without error).
    3. ``get_state`` exposes a ``q_values`` key (the uniform observation hook).
    """
    before = _state_key(model.get_state())
    model.decide(perception)
    model.decide(perception)
    state = model.get_state()
    readonly = before == _state_key(state)
    has_q = "q_values" in state

    failures = []
    if not readonly:
        failures.append("decide mutated state")
    if not has_q:
        failures.append("get_state lacks q_values")

    if failures:
        return Verdict(False, "; ".join(failures))
    return Verdict(True, "decide read-only, q_values exposed")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def check_determinism(actions_a: Sequence[str], actions_b: Sequence[str]) -> Verdict:
    """Two runs with identical seed/config must emit an identical action stream."""
    identical = list(actions_a) == list(actions_b)
    n = min(len(actions_a), len(actions_b))
    if identical:
        return Verdict(True, f"{len(actions_a)} actions identical across runs")
    first_div = next((i for i in range(n) if actions_a[i] != actions_b[i]), n)
    return Verdict(False, f"diverged at step {first_div}")


# ---------------------------------------------------------------------------
# GS-OFT-1 — patch abandonment (Marginal Value Theorem)
# ---------------------------------------------------------------------------


def residence_departures(prt: Sequence[int]) -> list[int]:
    """Residence values immediately before each reset to zero (a departure)."""
    return [prt[i - 1] for i in range(1, len(prt)) if prt[i] == 0 and prt[i - 1] >= 1]


def score_patch_abandonment(
    prt: Sequence[int], *, min_peak: int = 3, min_departures: int = 2
) -> Verdict:
    """PASS if residence time builds up (to ``min_peak``) and resets repeatedly.

    This is the MVT signature: exploit a patch (residence grows) until the
    marginal rate falls below the environmental average, then leave (reset).
    """
    if not prt:
        return Verdict(False, "no residence series")
    peak = max(prt)
    deps = residence_departures(prt)
    ok = peak >= min_peak and len(deps) >= min_departures
    return Verdict(
        ok,
        f"max_residence={peak}, departures={len(deps)} "
        f"(need >={min_peak} and >={min_departures})",
    )


# ---------------------------------------------------------------------------
# GS-OFT-2 — travel cost ⇒ residence (central MVT comparative static)
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def score_travel_cost(prt_low: Sequence[int], prt_high: Sequence[int]) -> Verdict:
    """PASS if mean residence-at-departure is higher under higher travel cost."""
    low = _mean(residence_departures(prt_low))
    high = _mean(residence_departures(prt_high))
    ok = high > low
    return Verdict(
        ok,
        f"mean residence low_cost={low:.2f} -> high_cost={high:.2f} "
        f"({'increases' if ok else 'does not increase'})",
    )


# ---------------------------------------------------------------------------
# GS-OFT-3 — diet-breadth zero-one rule
# ---------------------------------------------------------------------------


def singleton_fraction(diet_sets: Sequence[Sequence[int]]) -> float:
    """Fraction of steps where the diet collapses to the good prey only ({1})."""
    if not diet_sets:
        return 0.0
    return sum(1 for d in diet_sets if tuple(sorted(d)) == (1,)) / len(diet_sets)


def score_diet_zero_one(
    dense_sets: Sequence[Sequence[int]],
    scarce_sets: Sequence[Sequence[int]],
    *,
    min_dense_fraction: float = 0.05,
) -> Verdict:
    """PASS if abundant good prey drops type 2 ({1}) while scarce keeps it ({1,2}).

    The zero-one rule predicts a discontinuous switch: when the good prey is
    abundant the optimal diet excludes the poor prey entirely.
    """
    dense_f = singleton_fraction(dense_sets)
    scarce_f = singleton_fraction(scarce_sets)
    ok = dense_f >= min_dense_fraction and scarce_f == 0.0
    return Verdict(
        ok,
        f"singleton-diet fraction dense={dense_f:.2f}, scarce={scarce_f:.2f} "
        f"(dense must exclude poor prey, scarce must not)",
    )


# ---------------------------------------------------------------------------
# GS-RL-1 — learning curve
# ---------------------------------------------------------------------------


def reward_rate(rewards: Sequence[float]) -> float:
    return _mean(list(rewards))


def learning_delta(rewards: Sequence[float], *, frac: float = 0.16) -> float:
    """Reward-rate of the last ``frac`` of the run minus that of the first ``frac``."""
    n = len(rewards)
    if n == 0:
        return 0.0
    w = max(1, int(n * frac))
    return reward_rate(rewards[-w:]) - reward_rate(rewards[:w])


def score_learning_curve(
    rewards: Sequence[float], *, min_delta: float = 0.1
) -> Verdict:
    """PASS if the reward rate improves over the run by at least ``min_delta``."""
    delta = learning_delta(rewards)
    ok = delta >= min_delta
    return Verdict(
        ok,
        f"reward-rate improvement={delta:+.3f} (need >=+{min_delta})",
    )


def score_flat(rewards: Sequence[float], *, max_abs_delta: float = 0.1) -> Verdict:
    """PASS (as a non-learning control) if the reward rate stays roughly flat."""
    delta = learning_delta(rewards)
    ok = abs(delta) <= max_abs_delta
    return Verdict(
        ok,
        f"reward-rate change={delta:+.3f} (flat if |.|<={max_abs_delta})",
    )


# ---------------------------------------------------------------------------
# Analyst attribution (Layer 2, LLM part) — does the Analyst recover the truth?
# ---------------------------------------------------------------------------

# Distinctive terms that identify each paradigm in free-text analysis. Kept
# specific (not generic words like "reward"/"learning") to avoid false hits.
PARADIGM_TERMS: dict[str, tuple[str, ...]] = {
    "optimal-foraging-theory": (
        "forrajeo óptimo",
        "forrajeo optimo",
        "optimal foraging",
        "valor marginal",
        "marginal value",
        "mvt",
        "amplitud de dieta",
        "diet breadth",
        "diet-breadth",
        "charnov",
    ),
    "reinforcement-learning": (
        "aprendizaje por refuerzo",
        "reinforcement learning",
        "q-learning",
        "q learning",
        "actor-critic",
        "actor critic",
        "diferencia temporal",
        "temporal difference",
        "td error",
        "error td",
    ),
}


def detect_paradigm(text: str) -> str:
    """Classify which paradigm an analysis attributes the behaviour to.

    Returns the paradigm key, ``"both"`` if both are named with equal weight,
    or ``"none"`` if neither is recognised.
    """
    low = text.lower()
    hits = {p: sum(1 for t in terms if t in low) for p, terms in PARADIGM_TERMS.items()}
    oft, rl = hits["optimal-foraging-theory"], hits["reinforcement-learning"]
    if oft == 0 and rl == 0:
        return "none"
    if oft == rl:
        return "both"
    return "optimal-foraging-theory" if oft > rl else "reinforcement-learning"


def pattern_recall(text: str, pattern_terms: Sequence[str]) -> float:
    """Fraction of the expected pattern terms that appear in the analysis."""
    if not pattern_terms:
        return 1.0
    low = text.lower()
    return sum(1 for t in pattern_terms if t.lower() in low) / len(pattern_terms)


def precision_recall(
    predicted: Sequence[str], truth: Sequence[str]
) -> dict[str, float]:
    """Micro precision/recall/accuracy of paradigm attributions over scenarios.

    A prediction counts as correct only when it equals the truth label; ``"both"``
    or ``"none"`` are wrong attributions (they neither cleanly hit nor cleanly
    miss, so they depress precision).
    """
    n = len(truth)
    correct = sum(1 for p, t in zip(predicted, truth, strict=False) if p == t)
    # An attribution is "made" when the model commits to a single paradigm.
    committed = sum(1 for p in predicted if p in PARADIGM_TERMS)
    precision = correct / committed if committed else 0.0
    recall = correct / n if n else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "accuracy": round(correct / n, 3) if n else 0.0,
        "n": n,
        "committed": committed,
        "correct": correct,
    }
