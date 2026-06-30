"""Phase 1 model keys under test, shared across the benchmark runners.

Each key is the ``"{paradigm}/{formulation}"`` string that indexes the dict
returned by :func:`simlab.model_loader.discover_models`. Centralised here so a
Phase 1 rename is fixed in one place instead of in every runner script.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

MVT = "optimal-foraging-theory/marginal-value-theorem-with-continuous-energy-dynamics-ode-based"
DIET = "optimal-foraging-theory/diet-breadth-profitability-model-algebraic-threshold"
QL = "reinforcement-learning/tabular-q-learning-with-greedy-action-selection"
AC = "reinforcement-learning/actor-critic-with-softmax-policy"

# Short human-readable labels used in reports.
SHORT = {
    MVT: "MVT (forrajeo)",
    DIET: "Diet-breadth (forrajeo)",
    QL: "Q-learning (RL)",
    AC: "Actor-critic (RL)",
}

# Where every runner writes its report artefacts.
REPORTS = Path(__file__).parent / "reports"


# CASO1 (decisión basada en valor / neuroeconomía) — one representative
# formulation per paradigm. For drift-diffusion-model we use the Wiener-process
# formulation, not collapsing-boundary: Pazos's own LLM judge flagged the
# collapsing-boundary row as pointing at the wrong class.
CASO1 = [
    "attribute-based-value-computation/weighted-linear-summation-with-state-dependent-attribute-weights-algebraic",
    "dlpfc-self-control-modulation/attribute-reweighting-algebraic-model",
    "drift-diffusion-model/classical-wiener-process-with-per-action-accumulators",
    "goal-directed-vs-habitual-control/dual-q-table-with-fixed-exponential-decay-arbitration",
    "homeostatic-regulation-of-food-valuation/drive-reduction-ode-with-goal-directed-valuation",
    "pavlovian-control-of-food-approach/rescorlawagner-cached-value-agent-with-softmax-action-selection",
]

CASO1_SHORT = {
    CASO1[0]: "Valor por atributos (algebraico)",
    CASO1[1]: "Autocontrol dlPFC (reponderación)",
    CASO1[2]: "DDM (Wiener)",
    CASO1[3]: "Dirigido vs hábito (Q dual)",
    CASO1[4]: "Homeostasis (drive-reduction ODE)",
    CASO1[5]: "Pavloviano (Rescorla-Wagner softmax)",
}


def require_models(models: dict, keys: Iterable[str]) -> None:
    """Fail early with an actionable message if a required model is missing.

    Turns an opaque mid-run ``KeyError`` into a clear statement of which Phase 1
    formulations the restored state lacks.
    """
    missing = [k for k in keys if k not in models]
    if missing:
        raise SystemExit(
            "Modelos de la fase 1 no registrados: "
            + ", ".join(missing)
            + f"\nDisponibles: {sorted(models)}"
        )
