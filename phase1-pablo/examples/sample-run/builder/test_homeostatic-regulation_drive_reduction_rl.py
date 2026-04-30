"""
Tests for homeostatic-regulation_drive_reduction_rl model.
"""

import importlib.util
import math
import os
import random
import sys

# Load model from file with hyphens in its name
_MODULE_NAME = "homeostatic_regulation_drive_reduction_rl_model"
_spec = importlib.util.spec_from_file_location(
    _MODULE_NAME,
    os.path.join(
        os.path.dirname(__file__), "homeostatic-regulation_drive_reduction_rl_model.py"
    ),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod  # register BEFORE exec so @dataclass works
_spec.loader.exec_module(_mod)

HomeostaticDriveReductionRL = _mod.HomeostaticDriveReductionRL
Action = _mod.Action


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_perception(
    x=5, y=5, step=0, food=None, grid_w=10, grid_h=10, last_action_result=None
):
    return {
        "x": x,
        "y": y,
        "grid_width": grid_w,
        "grid_height": grid_h,
        "step": step,
        "resources": {"food": food or []},
        "last_action_result": last_action_result or {},
    }


# ---------------------------------------------------------------------------
# B1 – Drive increases as energy falls below set point without eating
# ---------------------------------------------------------------------------


def test_B1_drive_increases_without_eating():
    """Run 30 steps with no food → drive increases each step,
    and D = phi * (x - s)^2 at all times."""
    random.seed(42)
    model = HomeostaticDriveReductionRL()

    drives = []
    for i in range(30):
        action = Action(name="stay")
        perc = make_perception(step=i, last_action_result={})
        model.update(action, 0.0, perc)
        drives.append(model.D)
        # check algebraic relation R2
        assert abs(model.D - model.phi * (model.x - model.s) ** 2) < 1e-9, (
            f"D formula mismatch at step {i}"
        )

    # D should be monotonically non-decreasing (energy decays toward 0)
    for i in range(1, len(drives)):
        assert drives[i] >= drives[i - 1] - 1e-9, (
            f"Drive did not increase at step {i}: {drives[i - 1]} → {drives[i]}"
        )


# ---------------------------------------------------------------------------
# B2 – Eating produces positive reward when energy below set point
# ---------------------------------------------------------------------------


def test_B2_eating_positive_reward_below_setpoint():
    """At x=50, eat food (gaining delta_eat=15 → x after decay=64):
    r = D(50) - D(64) should be > 0."""
    model = HomeostaticDriveReductionRL()
    model.x = 50.0
    model.x_prev = 50.0

    action = Action(name="eat")
    perc = make_perception(last_action_result={"consumed": True})
    model.update(action, 1.0, perc)

    assert model.r > 0, f"Expected positive reward, got r={model.r}"
    # x after update = clamp(50 - 1 + 15, 0, 100) = 64
    expected_x = min(max(50.0 - 1.0 + 15.0, 0), 100)  # 64
    expected_r = (50.0 - 80.0) ** 2 - (expected_x - 80.0) ** 2
    assert abs(model.r - expected_r) < 1e-9, (
        f"Reward magnitude wrong: expected {expected_r}, got {model.r}"
    )


# ---------------------------------------------------------------------------
# B3 – Eating produces negative reward when energy overshoots set point
# ---------------------------------------------------------------------------


def test_B3_eating_negative_reward_above_setpoint():
    """At x=78, eat food (delta_eat=15, decay=1 → x=92):
    r = D_prev - D_curr should be < 0."""
    model = HomeostaticDriveReductionRL()
    model.x = 78.0
    model.x_prev = 78.0

    action = Action(name="eat")
    perc = make_perception(last_action_result={"consumed": True})
    model.update(action, 1.0, perc)

    assert model.r < 0, f"Expected negative reward, got r={model.r}"
    # x after: clamp(78 - 1 + 15, 0, 100) = 92
    expected_x = min(max(78.0 - 1.0 + 15.0, 0), 100)  # 92
    expected_r = (78.0 - 80.0) ** 2 - (expected_x - 80.0) ** 2
    assert abs(model.r - expected_r) < 1e-9, (
        f"Reward magnitude wrong: expected {expected_r}, got {model.r}"
    )


# ---------------------------------------------------------------------------
# B4 – Q-values converge: move_right valued higher when food is to the east
#
# We directly drive TD updates using the internal reward signal.
# Two episodes per iteration:
#   (A) agent takes 'move_right' → gets to eat → positive r
#   (B) agent takes 'move_left'  → no food, energy decays → negative r
# After many updates Q[state_E, 'move_right'] must exceed Q[state_E, 'move_left'].
# ---------------------------------------------------------------------------


def test_B4_q_values_converge_move_toward_food():
    """After many TD updates, Q[(low_bin,'E'), 'move_right'] > Q[(low_bin,'E'), 'move_left']."""
    random.seed(7)
    model = HomeostaticDriveReductionRL(
        td_learning_rate=0.3,
        discount_factor=0.9,
        softmax_inv_temperature=0.5,  # high exploration so all actions get updated
    )

    low_bin = 2
    state_E = (low_bin, "E")
    # x in [20,30) maps to bin 2  (n_bins=10, x_max=100)
    x_low = 25.0

    food_east = [{"x": 6, "y": 5, "type": "food", "palatability": 1.0}]

    for step in range(2000):
        # --- Episode A: take 'move_right', land on food, eat succeeds ---
        model.x = x_low
        model.x_prev = x_low
        model.z = state_E
        model.z_prev = state_E
        model.a_prev = "move_right"
        model._first_update = False

        # After moving right, agent is at (6,5) where food is
        # eat action succeeds → x increases
        perc_eat = make_perception(
            x=6, y=5, step=step, food=food_east, last_action_result={"consumed": True}
        )
        model.update(Action(name="eat"), 1.0, perc_eat)

        # --- Episode B: take 'move_left', no food ---
        model.x = x_low
        model.x_prev = x_low
        model.z = state_E
        model.z_prev = state_E
        model.a_prev = "move_left"
        model._first_update = False

        perc_no_eat = make_perception(
            x=4, y=5, step=step, food=food_east, last_action_result={"consumed": False}
        )
        model.update(Action(name="stay"), 0.0, perc_no_eat)

    key_right = (state_E, "move_right")
    key_left = (state_E, "move_left")
    q_right = model.Q.get(key_right, 0.0)
    q_left = model.Q.get(key_left, 0.0)
    assert q_right > q_left, (
        f"Expected Q[move_right]={q_right:.4f} > Q[move_left]={q_left:.4f}"
    )


# ---------------------------------------------------------------------------
# B5 – Agent prefers 'stay' when energy near set point after training
# ---------------------------------------------------------------------------


def test_B5_agent_prefers_stay_near_set_point():
    """Pre-load Q-values to strongly favour 'stay'; confirm it dominates."""
    random.seed(1)
    model = HomeostaticDriveReductionRL(softmax_inv_temperature=10.0)

    # Force high energy and state
    model.x = 79.0
    model.z = (model.n_bins - 1, "none")  # top energy bin, no food

    # Pre-load Q-values: strongly reward 'stay' in this state
    for a in ["move_up", "move_down", "move_left", "move_right", "eat"]:
        model.Q[(model.z, a)] = -5.0
    model.Q[(model.z, "stay")] = 10.0

    counts = {}
    N = 200
    for _ in range(N):
        perc = make_perception(x=5, y=5, step=0)
        act = model.decide(perc)
        counts[act.name] = counts.get(act.name, 0) + 1

    most_common = max(counts, key=lambda k: counts[k])
    assert most_common == "stay", (
        f"Expected 'stay' most common, got '{most_common}'. Counts: {counts}"
    )


# ---------------------------------------------------------------------------
# B6 – Softmax exploration: entropy decreases as Q-values differentiate
# ---------------------------------------------------------------------------


def test_B6_entropy_decreases_with_learning():
    """Action entropy after 500 training steps ≤ entropy after 10 steps."""

    def action_entropy(model, perc, n_samples=2000):
        counts = {}
        for _ in range(n_samples):
            a = model.decide(perc).name
            counts[a] = counts.get(a, 0) + 1
        probs = [c / n_samples for c in counts.values()]
        return -sum(p * math.log(p + 1e-12) for p in probs)

    food = [{"x": 6, "y": 5, "type": "food", "palatability": 1.0}]

    # --- early entropy (fresh model, 10 steps) ---
    random.seed(42)
    model_early = HomeostaticDriveReductionRL(softmax_inv_temperature=5.0)
    for step in range(10):
        perc = make_perception(x=5, y=5, step=step, food=food)
        a = model_early.decide(perc)
        model_early.update(
            a,
            0.0,
            make_perception(
                x=5, y=5, step=step, food=food, last_action_result={"consumed": False}
            ),
        )
    model_early.z = (0, "E")
    entropy_early = action_entropy(
        model_early, make_perception(x=5, y=5, step=10, food=food)
    )

    # --- late entropy (500 steps with real eat feedback) ---
    random.seed(42)
    model_late = HomeostaticDriveReductionRL(softmax_inv_temperature=5.0)
    for step in range(500):
        perc = make_perception(x=5, y=5, step=step, food=food)
        a = model_late.decide(perc)
        consumed = a.name == "eat"
        model_late.update(
            a,
            0.0,
            make_perception(
                x=5,
                y=5,
                step=step,
                food=food,
                last_action_result={"consumed": consumed},
            ),
        )
    model_late.z = (0, "E")
    entropy_late = action_entropy(
        model_late, make_perception(x=5, y=5, step=500, food=food)
    )

    assert entropy_late <= entropy_early, (
        f"Expected entropy to decrease with learning: "
        f"early={entropy_early:.4f}, late={entropy_late:.4f}"
    )
