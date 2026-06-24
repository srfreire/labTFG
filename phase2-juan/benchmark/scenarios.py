"""Golden-scenario environments for the Phase 2 behavioural benchmark.

These builders construct deterministic :class:`simlab.environment.Environment`
instances with *known ground truth* fixed by the theory each subject model
claims to implement. They are pure Python (no LLM, no DB) so the harness in
``run_golden_scenarios.py`` can drive any decision model through them and read
back per-step internal state.

Each builder returns an ``Environment`` with resources already placed but **no
agent** — the harness adds the agent (a Phase 1 model or a baseline) via
:func:`rollout`, which drives the loop and records, per step, the action taken,
the environment reward, and the model's ``get_state()`` snapshot.

The scenarios and their falsifiable predictions:

- ``GS-OFT-1`` patch abandonment: ``patch_residence_time`` rises while the agent
  exploits a patch and resets when it leaves — the Marginal Value Theorem
  leaving rule (Charnov, 1976).
- ``GS-OFT-2`` travel cost: higher ``travel_cost_per_move`` ⇒ longer mean patch
  residence before departure (the central comparative static of MVT).
- ``GS-OFT-3`` diet breadth: the diet model drops the low-profitability prey
  (``diet_set`` {1,2} → {1}) when the good prey becomes abundant — the zero-one
  rule (MacArthur & Pianka, 1966).
- ``GS-RL-1`` learning curve: reinforcement-learning models improve reward over
  time (and their TD error / exploration decay) while optimal-foraging models,
  which do not learn, stay flat.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simlab.environment import (
    ActionRule,
    Agent,
    ConsumeEffect,
    Environment,
    MoveEffect,
    NoopEffect,
    Position,
    Resource,
    ResourceRule,
)


def _forage_actions(eat_reward: float = 1.0) -> list[ActionRule]:
    """The standard 6-action foraging move set.

    Movement deltas follow the environment convention (y grows downward).
    Travel cost is modelled *inside* the subject models (they subtract their own
    ``travel_cost_per_move`` from internal energy), so environment moves carry no
    reward; only ``eat`` yields reward.
    """
    return [
        ActionRule("move_up", MoveEffect(0, -1)),
        ActionRule("move_down", MoveEffect(0, 1)),
        ActionRule("move_left", MoveEffect(-1, 0)),
        ActionRule("move_right", MoveEffect(1, 0)),
        ActionRule("stay", NoopEffect(0.0)),
        ActionRule("eat", ConsumeEffect("food", reward=eat_reward)),
    ]


def _place_food(
    env: Environment,
    positions: list[tuple[int, int]],
    *,
    palatability: float | None = None,
) -> None:
    """Place food resources at explicit grid positions (deterministic)."""
    for i, (x, y) in enumerate(positions):
        props: dict = {"type": "food"}
        if palatability is not None:
            props["palatability"] = palatability
        env.add_resource(
            Resource(id=f"food_fixed_{i}", position=Position(x, y), properties=props)
        )


@dataclass
class StepRecord:
    """One simulation step as seen by the harness."""

    step: int
    action: str
    reward: float
    state: dict


def rollout(
    model: object,
    env: Environment,
    *,
    steps: int,
    start: tuple[int, int] = (0, 0),
    agent_id: str = "subject",
) -> list[StepRecord]:
    """Drive ``model`` through ``env`` for ``steps`` and record each step.

    The model is wrapped in an :class:`Agent` at ``start`` and the environment's
    own ``step()`` loop is used unchanged, so the rollout exercises exactly the
    same code path as a real simulation. ``model_state`` is read from each
    emitted event (already numpy-flattened by the engine).
    """
    env.add_agent(Agent(id=agent_id, position=Position(*start), decision_model=model))
    records: list[StepRecord] = []
    for _ in range(steps):
        if env.is_finished():
            break
        events = env.step()
        for ev in events:
            if ev.agent_id != agent_id:
                continue
            records.append(
                StepRecord(
                    step=ev.step,
                    action=ev.action.name,
                    reward=float(ev.outcome.get("reward", 0.0)),
                    state=ev.outcome.get("model_state", {}),
                )
            )
    return records


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


# Fixed patch centres for the MVT scenarios — spread across the grid so that
# leaving one patch for the next incurs several moves (and thus travel cost).
_PATCH_CENTRES: list[tuple[int, int]] = [(2, 2), (9, 2), (2, 9), (9, 9), (6, 6)]


def build_patch_env(
    *,
    width: int = 12,
    height: int = 12,
    patches: int = 5,
    stack: int = 25,
    seed: int = 0,
) -> Environment:
    """GS-OFT-1 / GS-OFT-2: discrete patches the agent exploits then abandons.

    Each patch is a *stack* of ``stack`` food items at a single fixed cell, so
    the agent can eat in place across many steps (``patch_residence_time``
    grows) until the marginal return rate decays below the environmental
    threshold and it leaves for another patch (residence resets). Patches do not
    regenerate, so depletion is monotone within a patch and the agent must
    travel between the fixed centres — making ``travel_cost_per_move`` matter for
    GS-OFT-2.
    """
    env = Environment(
        width=width,
        height=height,
        actions=_forage_actions(),
        resources=[ResourceRule(type="food", count=0, regenerate=False)],
        seed=seed,
    )
    for cx, cy in _PATCH_CENTRES[:patches]:
        _place_food(env, [(cx, cy)] * stack)
    return env


def build_diet_env(
    *,
    width: int = 8,
    height: int = 8,
    high_per_cell: int,
    n_low: int,
    high_palatability: float = 0.9,
    low_palatability: float = 0.2,
    seed: int = 0,
) -> Environment:
    """GS-OFT-3: two prey qualities; *density* of the good prey is the treatment.

    High-palatability prey (>= the model's 0.5 threshold) is type 1; low is
    type 2. The diet model counts one encounter per food item *at the agent's
    cell*, so the encounter rate of type 1 (``λ₁``) is driven by how many high
    prey are stacked where the agent forages. When ``λ₁`` clears the zero-one
    threshold (``λ₁ > 2`` for these parameters) the model should drop type 2 from
    ``diet_set`` ({1,2} → {1}); when good prey is scarce, type 2 stays included.

    ``high_per_cell`` stacks that many type-1 items on a central column of cells
    (high density when large); ``n_low`` scatters type-2 items elsewhere.
    """
    env = Environment(
        width=width,
        height=height,
        actions=_forage_actions(),
        resources=[ResourceRule(type="food", count=0, regenerate=False)],
        seed=seed,
    )
    # Dense type-1 column through the middle so the forager keeps re-encountering
    # stacked good prey wherever it steps along it.
    cx = width // 2
    for cy in range(height):
        if high_per_cell > 0:
            _place_food(env, [(cx, cy)] * high_per_cell, palatability=high_palatability)
    rng = random.Random(seed)
    for _ in range(n_low):
        _place_food(
            env,
            [(rng.randint(0, width - 1), rng.randint(0, height - 1))],
            palatability=low_palatability,
        )
    return env


def build_learning_env(
    *,
    width: int = 2,
    height: int = 2,
    food_count: int = 4,
    seed: int = 0,
) -> Environment:
    """GS-RL-1: a compact *stationary* foraging task where reward can be learned.

    The tabular RL models encode state as ``(x, y, sorted relative-food
    offsets)`` — the *full* food set goes into the state key. Consuming food
    changes the food set, so for the state to recur (a prerequisite for tabular
    learning) the food *cardinality* must stay constant: with ``regenerate=True``
    the engine respawns one item per item eaten, holding the count fixed, and a
    tiny grid keeps the number of distinct food arrangements small enough that
    states actually repeat. Under these conditions a learner measurably improves
    its reward rate, a non-learning forager sits near its ceiling from step one,
    and a random agent stays at the floor — the contrast that makes the learning
    curve falsifiable.

    This regime is deliberately minimal: on larger grids, or with a depleting
    (non-regenerating) food supply, the variable-cardinality state encoding makes
    every state unique and *no* tabular model can learn — a limitation of the
    generated models that the benchmark documents rather than hides.
    """
    env = Environment(
        width=width,
        height=height,
        actions=_forage_actions(),
        resources=[ResourceRule(type="food", count=food_count, regenerate=True)],
        seed=seed,
    )
    return env
