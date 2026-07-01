"""Unit tests for the pure golden-scenario scoring functions.

These exercise the falsification logic on synthetic data — no model loading, no
services — so they run in the fast unit suite.
"""

from __future__ import annotations

from benchmark.baselines import GreedyForagerOracle, RandomModel
from benchmark.scoring import (
    check_contract,
    check_determinism,
    detect_paradigm,
    learning_delta,
    pattern_recall,
    precision_recall,
    residence_departures,
    score_diet_zero_one,
    score_flat,
    score_learning_curve,
    score_patch_abandonment,
    score_travel_cost,
    singleton_fraction,
)

PERCEPTION = {
    "x": 1,
    "y": 1,
    "grid_width": 4,
    "grid_height": 4,
    "step": 0,
    "resources": {"food": [{"x": 2, "y": 1}]},
    "last_action_result": {},
}


def test_contract_passes_for_readonly_model_with_q_values():
    v = check_contract(GreedyForagerOracle(seed=1), PERCEPTION)
    assert v.passed, v.detail


def test_contract_detects_missing_q_values():
    class NoQ:
        def decide(self, p):
            from benchmark.baselines import Action

            return Action("stay")

        def update(self, a, r, p):
            pass

        def get_state(self):
            return {"food_eaten": 0}

    v = check_contract(NoQ(), PERCEPTION)
    assert not v.passed
    assert "q_values" in v.detail


def test_contract_detects_decide_mutation():
    class Leaky:
        def __init__(self):
            self.calls = 0

        def decide(self, p):
            from benchmark.baselines import Action

            self.calls += 1  # decide mutates -> violates read-only
            return Action("stay")

        def update(self, a, r, p):
            pass

        def get_state(self):
            return {"q_values": {}, "calls": self.calls}

    v = check_contract(Leaky(), PERCEPTION)
    assert not v.passed
    assert "decide" in v.detail


def test_determinism_identical_streams():
    assert check_determinism(["a", "b", "c"], ["a", "b", "c"]).passed


def test_determinism_reports_divergence_point():
    v = check_determinism(["a", "b", "c"], ["a", "x", "c"])
    assert not v.passed
    assert "step 1" in v.detail


def test_residence_departures_extracts_pre_reset_peaks():
    assert residence_departures([0, 1, 2, 3, 0, 1, 0]) == [3, 1]


def test_patch_abandonment_pass_on_cycling_series():
    prt = [0, 1, 2, 3, 4, 0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 0]
    assert score_patch_abandonment(prt).passed


def test_patch_abandonment_fail_when_no_buildup():
    prt = [0, 1, 0, 1, 0, 1]  # peaks never reach min_peak=3
    assert not score_patch_abandonment(prt).passed


def test_travel_cost_pass_when_high_exceeds_low():
    low = [0, 2, 0, 2, 0]  # mean departure 2
    high = [0, 4, 0, 4, 0]  # mean departure 4
    assert score_travel_cost(low, high).passed


def test_travel_cost_fail_when_no_increase():
    assert not score_travel_cost([0, 3, 0, 3], [0, 2, 0, 2]).passed


def test_singleton_fraction_counts_good_prey_only_steps():
    sets = [[1, 2], [1], [1], [1, 2]]
    assert singleton_fraction(sets) == 0.5


def test_diet_zero_one_pass_when_dense_drops_poor_prey():
    dense = [[1, 2], [1], [1], [1]]
    scarce = [[1, 2], [1, 2], [1, 2]]
    assert score_diet_zero_one(dense, scarce).passed


def test_diet_zero_one_fail_when_scarce_also_drops():
    dense = [[1], [1]]
    scarce = [[1], [1, 2]]  # scarce should never collapse to {1}
    assert not score_diet_zero_one(dense, scarce).passed


def test_learning_delta_positive_for_improving_rewards():
    rewards = [0.0] * 50 + [1.0] * 50
    assert learning_delta(rewards) > 0.8


def test_learning_curve_pass_on_improvement():
    rewards = [0.0] * 100 + [1.0] * 100
    assert score_learning_curve(rewards).passed


def test_learning_curve_fail_on_flat_rewards():
    rewards = [0.3] * 200
    assert not score_learning_curve(rewards).passed


def test_flat_control_pass_for_steady_forager():
    rewards = [0.9] * 200
    assert score_flat(rewards).passed


def test_flat_control_fail_for_learner():
    rewards = [0.0] * 100 + [1.0] * 100
    assert not score_flat(rewards).passed


def test_detect_paradigm_oft():
    text = "El agente sigue el teorema del valor marginal (MVT): abandona el parche."
    assert detect_paradigm(text) == "optimal-foraging-theory"


def test_detect_paradigm_rl():
    text = (
        "Comportamiento de aprendizaje por refuerzo; el error TD decae con Q-learning."
    )
    assert detect_paradigm(text) == "reinforcement-learning"


def test_detect_paradigm_none():
    assert detect_paradigm("El agente se mueve por la rejilla y come.") == "none"


def test_pattern_recall_fraction():
    text = "Se observa abandono de parche y aumento del tiempo de residencia."
    assert (
        pattern_recall(text, ["abandono de parche", "residencia", "no-aparece"])
        == 2 / 3
    )


def test_precision_recall_perfect():
    truth = ["optimal-foraging-theory", "reinforcement-learning"]
    pred = ["optimal-foraging-theory", "reinforcement-learning"]
    m = precision_recall(pred, truth)
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["accuracy"] == 1.0


def test_precision_recall_with_uncommitted_attribution():
    truth = [
        "optimal-foraging-theory",
        "reinforcement-learning",
        "reinforcement-learning",
    ]
    pred = ["optimal-foraging-theory", "none", "reinforcement-learning"]
    m = precision_recall(pred, truth)
    assert m["precision"] == 1.0
    assert m["recall"] == round(2 / 3, 3)


def test_random_model_is_not_flagged_as_learning():
    rng_rewards = [(i * 7) % 3 == 0 for i in range(400)]
    rewards = [1.0 if b else 0.0 for b in rng_rewards]
    assert not score_learning_curve(rewards).passed
    _ = RandomModel  # imported model is contract-checked elsewhere
