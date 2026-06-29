"""
Tests for ActiveInferenceWithExpectedFreeEnergyProbabilisticPolicySelectionModel

Each test maps to one expected_behavior in the spec.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from active_inference_with_expected_free_energy_probabilistic_policy_selection_model import (
    ActiveInferenceWithExpectedFreeEnergyProbabilisticPolicySelectionModel,
    Action,
)

Model = ActiveInferenceWithExpectedFreeEnergyProbabilisticPolicySelectionModel

# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def make_perception(
    x=5, y=5,
    grid_width=20, grid_height=20,
    step=0,
    food_positions=None,
    last_action_result=None,
):
    food_positions = food_positions or []
    food_resources = [{"x": fx, "y": fy} for fx, fy in food_positions]
    return {
        "x": x, "y": y,
        "grid_width": grid_width, "grid_height": grid_height,
        "step": step,
        "resources": {"food": food_resources},
        "last_action_result": last_action_result or {},
    }


def make_model(**kwargs):
    return Model(**kwargs)


def prime_belief_with_food(model, ax=5, ay=5, n_steps=8):
    """
    Run update() with food_here (obs=1) observations so belief concentrates
    on FOOD_PRESENT states at center.
    """
    perception = make_perception(x=ax, y=ay, food_positions=[(ax, ay)])
    stay = Action(name="stay")
    for _ in range(n_steps):
        model.update(stay, 0.0, perception)


# ------------------------------------------------------------------ #
#  B1 – Hungry agent seeks food                                        #
# ------------------------------------------------------------------ #

def test_b1_hungry_agent_prefers_food_actions():
    """
    B1: With H > 0.5 and food at the agent's position, pragmatic EFE
    should favour eat/stay (food-directed) over pure movement actions.
    """
    model = make_model(seed=42, omega=0.2, beta_G=6.0)
    model.H = 0.8
    prime_belief_with_food(model, ax=5, ay=5, n_steps=10)

    perception = make_perception(x=5, y=5, food_positions=[(5, 5)])

    food_directed = 0
    n_trials = 60
    for _ in range(n_trials):
        a = model.decide(perception)
        if a.name in ("eat", "stay"):
            food_directed += 1

    ratio = food_directed / n_trials
    assert ratio > 0.5, (
        f"Expected eat/stay > 50% when hungry and food here, got {ratio:.2%}"
    )


# ------------------------------------------------------------------ #
#  B2 – Sated agent explores                                           #
# ------------------------------------------------------------------ #

def test_b2_sated_agent_explores():
    """
    B2: With omega=0.9 and H≈0, action distribution should be more uniform
    (higher entropy) than with omega=0 and high hunger.
    """
    def action_entropy(model, perception, n=200):
        counts = {a: 0 for a in model.ACTIONS}
        for _ in range(n):
            counts[model.decide(perception).name] += 1
        total = n
        h = 0.0
        for c in counts.values():
            p = c / total
            if p > 0:
                h -= p * math.log(p)
        return h

    perception = make_perception(x=5, y=5, food_positions=[])

    model_explore = make_model(seed=1, omega=0.9, beta_G=2.0)
    model_explore.H = 0.0
    h_explore = action_entropy(model_explore, perception)

    model_exploit = make_model(seed=1, omega=0.0, beta_G=2.0)
    model_exploit.H = 0.9
    h_exploit = action_entropy(model_exploit, perception)

    assert h_explore >= h_exploit - 0.3, (
        f"Sated epistemic agent entropy ({h_explore:.3f}) should not be "
        f"lower than hungry exploiting agent ({h_exploit:.3f}) by more than 0.3"
    )


# ------------------------------------------------------------------ #
#  B3 – Agent eats when on food and hungry                             #
# ------------------------------------------------------------------ #

def test_b3_eat_when_on_food_and_hungry():
    """
    B3: When food is at the agent's position and H is high, 'eat' should
    be selected frequently.

    With the FOOD_JUST_ATE transient state, eating leads to A[0][·] >> A[7][·]
    at the center, meaning Q_o(eat) concentrates on obs 0 (food_here+just_ate)
    which is the MOST preferred outcome under high hunger. This makes
    G_prag(eat) small, so eat should win under pragmatic pressure.
    """
    model = make_model(seed=7, omega=0.1, beta_G=8.0)
    model.H = 0.8
    prime_belief_with_food(model, ax=5, ay=5, n_steps=12)

    perception = make_perception(x=5, y=5, food_positions=[(5, 5)])

    eat_count = sum(1 for _ in range(80) if model.decide(perception).name == "eat")
    eat_prob = eat_count / 80

    assert eat_prob > 0.5, (
        f"Expected eat > 50% when food present and hungry (belief primed), "
        f"got {eat_prob:.2%}"
    )


# ------------------------------------------------------------------ #
#  B4 – Hunger dynamics                                                #
# ------------------------------------------------------------------ #

def test_b4_hunger_increases_and_decreases():
    """
    B4: Hunger grows without eating and drops after eating.
    """
    model = make_model()
    model.H = 0.0
    perception = make_perception()
    stay = Action(name="stay")

    for _ in range(20):
        model.update(stay, 0.0, perception)

    assert model.H > 0.5, (
        f"Hunger should exceed 0.5 after 20 no-food steps, got {model.H:.3f}"
    )

    H_before = model.H
    model.update(Action(name="eat"), 1.0, perception)
    H_after = model.H

    assert H_after < H_before, f"Hunger should drop after eating: {H_after:.3f} >= {H_before:.3f}"
    expected_decrease = model.delta_H - model.alpha_H
    actual_decrease = H_before - H_after
    assert abs(actual_decrease - expected_decrease) < 0.05, (
        f"Expected decrease ~{expected_decrease:.3f}, got {actual_decrease:.3f}"
    )


# ------------------------------------------------------------------ #
#  B5 – Likelihood matrix A improves over time                         #
# ------------------------------------------------------------------ #

def test_b5_likelihood_matrix_improves():
    """
    B5: A column entropy should not increase after 200 learning steps
    (columns become more peaked as generative model sharpens).
    """
    random.seed(42)
    model = make_model(seed=42, alpha_B=0.1)

    def col_entropy(A, k):
        h = 0.0
        for o in range(len(A)):
            p = A[o][k]
            if p > 1e-12:
                h -= p * math.log(p)
        return h

    early, late = [], []
    food_positions = [(5, 5)]
    for step in range(200):
        perception = make_perception(x=5, y=5, food_positions=food_positions, step=step)
        action = model.decide(perception)
        reward = 1.0 if action.name == "eat" and (5, 5) in food_positions else 0.0
        model.update(action, reward, perception)

        avg_e = sum(col_entropy(model.A, k) for k in range(model.K)) / model.K
        if step < 50:
            early.append(avg_e)
        elif step >= 150:
            late.append(avg_e)

    mean_early = sum(early) / len(early)
    mean_late = sum(late) / len(late)

    assert mean_late <= mean_early + 0.1, (
        f"A column entropy should not increase after learning. "
        f"Early: {mean_early:.4f}, Late: {mean_late:.4f}"
    )


# ------------------------------------------------------------------ #
#  B6 – omega controls exploration–exploitation                        #
# ------------------------------------------------------------------ #

def test_b6_omega_controls_exploration_exploitation():
    """
    B6: omega=0 (pure pragmatic) with high hunger should strongly prefer
    food actions (eat/stay) compared to omega=1 (pure epistemic).
    """
    def food_action_ratio(omega_val, seed=0, n=100):
        random.seed(seed)
        m = make_model(omega=omega_val, seed=seed, beta_G=5.0)
        m.H = 0.8
        prime_belief_with_food(m, ax=5, ay=5, n_steps=10)
        perception = make_perception(x=5, y=5, food_positions=[(5, 5)])
        count = sum(1 for _ in range(n) if m.decide(perception).name in ("eat", "stay"))
        return count / n

    ratio_exploit = food_action_ratio(omega_val=0.0)
    ratio_explore = food_action_ratio(omega_val=1.0)

    # Exploitation (omega=0) must show strong food preference
    assert ratio_exploit >= 0.5, (
        f"omega=0 + high hunger should select eat/stay >= 50%, got {ratio_exploit:.2%}"
    )
    # Exploitation should select food actions at least as often as exploration
    assert ratio_exploit >= ratio_explore * 0.6, (
        f"omega=0 (exploit={ratio_exploit:.2%}) should be >= 60% of "
        f"omega=1 (explore={ratio_explore:.2%})"
    )


# ------------------------------------------------------------------ #
#  B7 – Bayesian belief update                                         #
# ------------------------------------------------------------------ #

def test_b7_bayesian_belief_update():
    """
    B7: After observing food_here (o=1), posterior on FOOD_PRESENT-at-center
    should be higher than the prior.
    """
    model = make_model()
    assert abs(sum(model.s_prior) - 1.0) < 1e-6, "Prior must be normalized"

    prior_food = sum(model.s_prior[k] for k in model.food_at_center_states)

    updated = model._bayesian_update(1)  # obs 1 = food_here + not_ate
    post_food = sum(updated[k] for k in model.food_at_center_states)

    assert post_food > prior_food, (
        f"Posterior on food-at-center ({post_food:.4f}) should exceed "
        f"prior ({prior_food:.4f})"
    )
    assert post_food > 0.3, (
        f"Expected food-at-center posterior > 0.3 after food_here obs, "
        f"got {post_food:.4f}"
    )


# ------------------------------------------------------------------ #
#  Structural / contract tests                                         #
# ------------------------------------------------------------------ #

def test_get_state_includes_q_values():
    model = make_model()
    state = model.get_state()
    assert "q_values" in state
    qv = state["q_values"]
    for a in model.ACTIONS:
        assert a in qv, f"q_values missing key '{a}'"
        assert isinstance(qv[a], float)


def test_decide_is_readonly():
    model = make_model(seed=99)
    perception = make_perception(x=5, y=5, food_positions=[(5, 5)])

    H_before = model.H
    sb_before = list(model.s_belief)

    for _ in range(10):
        model.decide(perception)

    assert model.H == H_before, "decide() must not change H"
    assert model.s_belief == sb_before, "decide() must not change s_belief"


def test_update_changes_hunger():
    model = make_model()
    model.H = 0.5
    perception = make_perception()

    model.update(Action("stay"), 0.0, perception)
    assert model.H > 0.5, "Hunger should increase after no-food step"

    model.H = 0.5
    model.update(Action("eat"), 1.0, perception)
    assert model.H < 0.5, "Hunger should decrease after eating"


def test_belief_is_always_normalized():
    model = make_model(seed=0)
    perception = make_perception(x=5, y=5, food_positions=[(5, 5)])
    stay = Action(name="stay")
    for _ in range(30):
        model.decide(perception)
        model.update(stay, 0.0, perception)
    assert abs(sum(model.s_belief) - 1.0) < 1e-6, "Belief must stay normalized"


def test_A_columns_normalized():
    model = make_model()
    for k in range(model.K):
        col_sum = sum(model.A[o][k] for o in range(model.N_obs))
        assert abs(col_sum - 1.0) < 1e-6, f"A col {k} should sum to 1 at init"

    perception = make_perception(x=5, y=5, food_positions=[(5, 5)])
    for _ in range(10):
        model.update(Action("stay"), 0.0, perception)

    for k in range(model.K):
        col_sum = sum(model.A[o][k] for o in range(model.N_obs))
        assert abs(col_sum - 1.0) < 1e-5, f"A col {k} should stay normalized after updates"


def test_preferred_outcomes_normalized():
    model = make_model()
    for H in [0.0, 0.3, 0.6, 0.9]:
        C = model._compute_preferred_outcomes(H)
        assert abs(sum(C) - 1.0) < 1e-6, f"C should sum to 1 for H={H}"
        if H > 0.7:
            food_mass = C[0] + C[1]
            other_mass = sum(C[4:])
            assert food_mass > other_mass, (
                f"At H={H}, food observations should dominate"
            )


def test_action_always_valid():
    model = make_model(seed=77)
    valid = set(model.ACTIONS)
    for i in range(30):
        p = make_perception(x=random.randint(0, 19), y=random.randint(0, 19), step=i)
        a = model.decide(p)
        assert a.name in valid, f"Invalid action: {a.name}"


def test_transition_matrix_columns_sum_to_one():
    model = make_model()
    K = model.K
    for action in model.ACTIONS:
        B_a = model.B[action]
        for k in range(K):
            col_sum = sum(B_a[kp][k] for kp in range(K))
            assert abs(col_sum - 1.0) < 1e-9, (
                f"B[{action}] col {k} should sum to 1, got {col_sum:.6f}"
            )


def test_eat_transitions_to_just_ate_state():
    """
    After eat action with food-at-center belief, predicted next state
    should concentrate on FOOD_JUST_ATE-at-center.
    """
    model = make_model()
    cs_food = model._state_idx(model.CENTER_IDX, model.FOOD_PRESENT)
    model.s_belief = [0.0] * model.K
    model.s_belief[cs_food] = 1.0

    s_next = model._predict_next_state("eat", model.s_belief)
    cs_just_ate = model._state_idx(model.CENTER_IDX, model.FOOD_JUST_ATE)

    assert s_next[cs_just_ate] > 0.99, (
        f"eat with food-at-center should transition to FOOD_JUST_ATE, "
        f"got {s_next[cs_just_ate]:.4f}"
    )


def test_just_ate_state_produces_preferred_observation():
    """
    A[0][FOOD_JUST_ATE at center] should be the highest-probability obs
    for that state, reflecting that eating produces obs 0 (food_here+just_ate).
    """
    model = make_model()
    k = model._state_idx(model.CENTER_IDX, model.FOOD_JUST_ATE)
    probs = [model.A[o][k] for o in range(model.N_obs)]
    best_obs = max(range(model.N_obs), key=lambda o: probs[o])
    assert best_obs == 0, (
        f"FOOD_JUST_ATE at center should map to obs 0 (food_here+just_ate), "
        f"got obs {best_obs} with probs {probs}"
    )


def test_efe_eat_lower_than_move_when_very_hungry_and_food_present():
    """
    Direct EFE comparison: when belief is concentrated on food-at-center
    and H is very high (C strongly prefers obs 0), G_prag(eat) should be
    lower than G_prag(move_up) under pure pragmatic (omega=0).
    """
    model = make_model(omega=0.0)
    model.H = 0.95
    C = model._compute_preferred_outcomes(model.H)

    # Certain belief: food present at center
    cs_food = model._state_idx(model.CENTER_IDX, model.FOOD_PRESENT)
    model.s_belief = [0.0] * model.K
    model.s_belief[cs_food] = 1.0

    G_eat, G_prag_eat, _ = model._compute_efe("eat", model.s_belief, C)
    G_move_up, G_prag_move_up, _ = model._compute_efe("move_up", model.s_belief, C)

    assert G_eat < G_move_up, (
        f"EFE(eat)={G_eat:.4f} should be < EFE(move_up)={G_move_up:.4f} "
        f"when food is certain at center and hunger is very high"
    )
