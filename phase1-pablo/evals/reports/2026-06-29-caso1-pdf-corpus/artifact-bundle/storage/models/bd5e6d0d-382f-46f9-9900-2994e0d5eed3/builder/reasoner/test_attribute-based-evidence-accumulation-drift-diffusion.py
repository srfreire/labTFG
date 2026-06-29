"""
Tests for AttributeBasedEvidenceAccumulationDriftDiffusionModel
covering all five expected behaviors (B1–B5).
"""

import sys
import os
import random
import math

# Ensure module is importable (PYTHONPATH is set to builder/reasoner)
sys.path.insert(0, os.path.dirname(__file__))

# Module name has hyphens — use importlib
import importlib
mod = importlib.import_module(
    "attribute-based-evidence-accumulation-drift-diffusion_model"
)
AttributeBasedEvidenceAccumulationDriftDiffusionModel = (
    mod.AttributeBasedEvidenceAccumulationDriftDiffusionModel
)
Action = mod.Action


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_perception(
    x=5, y=5, grid_width=10, grid_height=10, food=None, step=0, last_action_result=None
):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


# ---------------------------------------------------------------------------
# B1: Hungry agent biases toward closer food
# ---------------------------------------------------------------------------

def test_b1_hungry_prefers_closer_food():
    """
    With high hunger (H_t=0.9), w_imm is high, so the agent should prefer
    actions that move toward the closer food more often than toward the far one.

    Setup: agent at (5,5), grid 10x10.
      - Near food at (5,4): one step above, so move_up leads there (dist=0 from next cell).
      - Far food at (5,9): 4 steps below with low palatability (palatability=0.1 so a_abs<0).
    With high hunger w_imm dominates: move_up (near food, dist=0 from next cell -> a_imm high)
    should win significantly more often than move_down (far food, a_imm low, a_abs negative).
    """
    random.seed(0)
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    model.H_t = 0.9

    # Near food directly above agent, far food far below with low palatability
    food = [
        {"x": 5, "y": 4, "type": "food", "palatability": 0.5},   # near: 0 steps from (5,4)
        {"x": 5, "y": 9, "type": "food", "palatability": 0.1},   # far: 4 steps from (5,6), negative a_abs
    ]
    perception = make_perception(x=5, y=5, food=food)

    # Check the drift rates directly to verify model logic
    w_imm, w_abs = model._compute_attr_weights()
    _, drift, _, _ = model._compute_attr_values(perception, w_imm, w_abs)

    # move_up toward near food (dist=0 from (5,4)) should have higher drift
    # than move_down toward far food
    assert drift["move_up"] > drift["move_down"], (
        f"With high hunger, move_up drift ({drift['move_up']:.4f}) should exceed "
        f"move_down drift ({drift['move_down']:.4f})"
    )

    # Now verify statistically: move_up should be chosen more than move_down
    n = 300
    choices = [model.decide(perception).name for _ in range(n)]
    up_count = choices.count("move_up")
    down_count = choices.count("move_down")

    assert up_count > down_count, (
        f"Expected move_up ({up_count}) > move_down ({down_count}) for hungry agent near close food"
    )


# ---------------------------------------------------------------------------
# B2: High attribute conflict → higher choice entropy
# ---------------------------------------------------------------------------

def _entropy(choices, all_actions):
    from collections import Counter
    counts = Counter(choices)
    n = len(choices)
    ent = 0.0
    for a in all_actions:
        p = counts.get(a, 0) / n
        if p > 0:
            ent -= p * math.log(p)
    return ent


def test_b2_high_conflict_more_entropy():
    """
    Low palatability food (0.1) → a_abs ≈ -1, a_imm=1 (if close) → high conflict.
    High palatability food (1.0) → a_abs ≈ +1, a_imm=1 → low conflict.
    High-conflict scenario should yield higher choice entropy.
    """
    all_actions = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]

    # High conflict: low palatability food directly on agent position
    model_hc = AttributeBasedEvidenceAccumulationDriftDiffusionModel(
        base_noise=0.3, conflict_noise_scaling=0.5
    )
    model_hc.H_t = 0.5
    food_hc = [{"x": 5, "y": 5, "type": "food", "palatability": 0.1}]
    perc_hc = make_perception(x=5, y=5, food=food_hc)

    # Low conflict: high palatability food directly on agent
    model_lc = AttributeBasedEvidenceAccumulationDriftDiffusionModel(
        base_noise=0.3, conflict_noise_scaling=0.5
    )
    model_lc.H_t = 0.5
    food_lc = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
    perc_lc = make_perception(x=5, y=5, food=food_lc)

    n = 300
    random.seed(99)
    choices_hc = [model_hc.decide(perc_hc).name for _ in range(n)]
    random.seed(99)
    choices_lc = [model_lc.decide(perc_lc).name for _ in range(n)]

    ent_hc = _entropy(choices_hc, all_actions)
    ent_lc = _entropy(choices_lc, all_actions)

    assert ent_hc > ent_lc, (
        f"Expected higher entropy under conflict ({ent_hc:.3f}) vs no-conflict ({ent_lc:.3f})"
    )


# ---------------------------------------------------------------------------
# B3: Agent eats when on the same cell as food
# ---------------------------------------------------------------------------

def test_b3_eat_drift_is_maximal_when_on_food():
    """
    B3 primary check: eat action must have the strictly highest drift rate
    when the agent is on the food cell at a non-boundary position.

    At center (5,5) with food at (5,5), palatability=0.9:
      - eat: a_imm=1.0, a_abs≈+0.78 → drift = w_imm*1 + w_abs*0.78 (highest possible)
      - move_X: a_imm = 1 - 1/max_dist ≈ 0.944 (dist=1 to same food from next cell)
    So eat strictly dominates in drift.
    """
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    model.H_t = 0.5

    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.9}]
    perception = make_perception(x=5, y=5, food=food)

    w_imm, w_abs = model._compute_attr_weights()
    _, drift, _, _ = model._compute_attr_values(perception, w_imm, w_abs)

    assert drift["eat"] == max(drift.values()), (
        f"Eat should have max drift when on food at center, got {drift}"
    )
    # Also verify eat strictly beats every single movement
    for a in ["move_up", "move_down", "move_left", "move_right"]:
        assert drift["eat"] > drift[a], (
            f"Eat drift ({drift['eat']:.4f}) should exceed {a} drift ({drift[a]:.4f})"
        )


def test_b3_eat_most_chosen_action():
    """
    B3 statistical check: eat should be chosen more often than any single
    competitor when on a food cell with high palatability at a central position.

    The 6-way race means no single action dominates with >50%, but the action
    with the highest drift (eat) should be selected most frequently.
    """
    random.seed(42)
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    model.H_t = 0.5

    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.9}]
    perception = make_perception(x=5, y=5, food=food)

    n = 1000
    choices = [model.decide(perception).name for _ in range(n)]
    from collections import Counter
    counts = Counter(choices)

    eat_count = counts.get("eat", 0)
    # eat should beat each individual competitor (not necessarily all combined)
    for a in ["move_up", "move_down", "move_left", "move_right", "stay"]:
        assert eat_count > counts.get(a, 0), (
            f"Eat ({eat_count}) should beat {a} ({counts.get(a,0)}) as it has highest drift. "
            f"Full counts: {dict(counts)}"
        )


# ---------------------------------------------------------------------------
# B4: Zero-conflict → faster decisions (fewer deliberation steps)
# ---------------------------------------------------------------------------

def _count_steps_to_threshold(model, perception, theta, n_trials=200, seed=0):
    """
    Run evidence accumulation manually and count deliberation steps until
    the first accumulator crosses theta. Returns list of step counts.
    """
    all_actions = ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]
    random.seed(seed)

    T_max = model.T_max

    step_counts = []
    for _ in range(n_trials):
        w_imm, w_abs = model._compute_attr_weights()
        attr_values, drift, conflict, noise = model._compute_attr_values(
            perception, w_imm, w_abs
        )

        E = {a: 0.0 for a in all_actions}
        crossed = None
        for t in range(1, T_max + 1):
            for a in all_actions:
                xi = random.gauss(0, 1)
                E[a] += drift[a] + noise[a] * xi
                if crossed is None and E[a] >= theta:
                    crossed = t
            if crossed is not None:
                break
        step_counts.append(crossed if crossed is not None else T_max)

    return step_counts


def test_b4_low_conflict_faster_decisions():
    """
    Low-conflict scenario (high palatability + close food → a_imm≈a_abs≈+1)
    should reach threshold faster than high-conflict scenario.
    """
    theta = 1.0
    T_max = 20

    # Low conflict: food at same cell, high palatability → a_imm=1.0, a_abs≈+1.0
    model_lc = AttributeBasedEvidenceAccumulationDriftDiffusionModel(
        decision_threshold=theta, max_deliberation_steps=T_max
    )
    model_lc.H_t = 0.5
    food_lc = [{"x": 5, "y": 5, "type": "food", "palatability": 1.0}]
    perc_lc = make_perception(x=5, y=5, food=food_lc)

    # High conflict: food at same cell, low palatability → a_imm=1.0, a_abs≈-1.0
    model_hc = AttributeBasedEvidenceAccumulationDriftDiffusionModel(
        decision_threshold=theta, max_deliberation_steps=T_max,
        conflict_noise_scaling=1.5  # amplify conflict effect
    )
    model_hc.H_t = 0.5
    food_hc = [{"x": 5, "y": 5, "type": "food", "palatability": 0.1}]
    perc_hc = make_perception(x=5, y=5, food=food_hc)

    steps_lc = _count_steps_to_threshold(model_lc, perc_lc, theta, n_trials=500, seed=17)
    steps_hc = _count_steps_to_threshold(model_hc, perc_hc, theta, n_trials=500, seed=17)

    mean_lc = sum(steps_lc) / len(steps_lc)
    mean_hc = sum(steps_hc) / len(steps_hc)

    assert mean_lc < mean_hc, (
        f"Expected low-conflict steps ({mean_lc:.2f}) < high-conflict steps ({mean_hc:.2f})"
    )


# ---------------------------------------------------------------------------
# B5: Hunger rises without eating; w_imm shifts upward
# ---------------------------------------------------------------------------

def test_b5_hunger_rises_without_eating():
    """
    After 100 update steps with no food consumption, H_t should exceed 0.95
    and w_imm should be higher than the initial value (0.5).

    Note: the R1 formula gives w_imm = (1+H)/(2+H).
    At H=1.0 (max), w_imm = 2/3 ≈ 0.667.
    So we assert w_imm > 0.6 (clearly above initial 0.5) which is the correct
    mathematical behaviour of the spec formula.
    """
    random.seed(123)
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel(
        hunger_rise_rate=0.01
    )
    model.H_t = 0.0   # start sated

    # Empty perception — no food anywhere
    perception = make_perception(x=5, y=5, food=[])
    new_perception = make_perception(
        x=5, y=5, food=[], last_action_result={"consumed": False}
    )

    for _ in range(100):
        action = model.decide(perception)
        model.update(action, 0.0, new_perception)

    state = model.get_state()
    H = state["hunger"]
    w_imm = state["immediate_weight"]

    assert H > 0.95, f"Expected H_t > 0.95 after 100 steps, got {H:.4f}"
    # At H≈1.0, formula gives w_imm=(1+1)/(2+1)=2/3≈0.667, clearly above initial 0.5
    assert w_imm > 0.6, f"Expected w_imm > 0.6 when very hungry, got {w_imm:.4f}"


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

def test_get_state_has_q_values():
    """get_state() must always include q_values dict."""
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    state = model.get_state()
    assert "q_values" in state
    assert isinstance(state["q_values"], dict)
    assert len(state["q_values"]) == 6  # 6 actions


def test_decide_returns_action():
    """decide() returns an Action with a valid action name."""
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    perception = make_perception()
    a = model.decide(perception)
    assert isinstance(a, Action)
    assert a.name in ["move_up", "move_down", "move_left", "move_right", "stay", "eat"]


def test_update_modifies_hunger():
    """After eating, hunger should decrease."""
    random.seed(0)
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    model.H_t = 0.8

    food = [{"x": 3, "y": 3, "type": "food", "palatability": 0.9}]
    perception = make_perception(x=3, y=3, food=food)
    action = Action(name="eat")
    new_perception = make_perception(
        x=3, y=3, food=food,
        last_action_result={"consumed": True}
    )
    model.update(action, 1.0, new_perception)

    assert model.H_t < 0.8, (
        f"Hunger should decrease after eating, but got {model.H_t:.4f}"
    )


def test_weights_sum_to_one():
    """w_imm + w_abs should always sum to 1.0 after update."""
    random.seed(5)
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    food = [{"x": 5, "y": 5, "type": "food", "palatability": 0.7}]
    perception = make_perception(x=5, y=5, food=food)
    new_perception = make_perception(
        x=5, y=5, food=food,
        last_action_result={"consumed": True}
    )

    for _ in range(20):
        a = model.decide(perception)
        model.update(a, 1.0, new_perception)

    total = model.w_imm + model.w_abs
    assert abs(total - 1.0) < 1e-9, f"Weights should sum to 1.0, got {total}"


def test_no_food_no_eat():
    """Without food at agent position, eat action should have zero drift."""
    model = AttributeBasedEvidenceAccumulationDriftDiffusionModel()
    model.H_t = 0.5
    perception = make_perception(x=5, y=5, food=[])
    w_imm, w_abs = model._compute_attr_weights()
    attr_values, drift, _, _ = model._compute_attr_values(perception, w_imm, w_abs)
    assert drift["eat"] == 0.0, f"Expected eat drift=0 with no food, got {drift['eat']}"


if __name__ == "__main__":
    test_b1_hungry_prefers_closer_food()
    print("B1 passed")
    test_b2_high_conflict_more_entropy()
    print("B2 passed")
    test_b3_eat_drift_is_maximal_when_on_food()
    print("B3a passed")
    test_b3_eat_most_chosen_action()
    print("B3b passed")
    test_b4_low_conflict_faster_decisions()
    print("B4 passed")
    test_b5_hunger_rises_without_eating()
    print("B5 passed")
    test_get_state_has_q_values()
    print("get_state q_values passed")
    test_decide_returns_action()
    print("decide returns Action passed")
    test_update_modifies_hunger()
    print("update modifies hunger passed")
    test_weights_sum_to_one()
    print("weights sum to 1 passed")
    test_no_food_no_eat()
    print("no food no eat passed")
    print("All tests passed!")
