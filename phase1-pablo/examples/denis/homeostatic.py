"""Homeostatic model — ODE system from Denis TFM (section 2.2).

Tracks fat reserves (F), glycogen (Gly), ghrelin (G), leptin (L).
Produces a hunger signal H(t) = max(0, G - Leff).

References:
    - Jacquier et al. (2014) — ODE model of body weight and food intake
    - Denis Yamunaque TFM (2025) — Section 2.2
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from decisionlab.models.protocol import STAY, Action, Perception


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class HomeostaticParams:
    # Initial values (Table 2.1)
    fat_init: float = 50.0
    glycogen_init: float = 20.0
    ghrelin_init: float = 0.1
    leptin_init: float = 0.8
    hunger_init: float = 0.5

    # Storage capacities
    fat_max: float = 100.0
    glycogen_max: float = 50.0

    # Conversion rates (energy -> storage)
    c_fat: float = 0.3
    c_glycogen: float = 0.5

    # Utilization rates
    alpha_fat: float = 0.01  # K_F from Table 2.1
    alpha_glycogen: float = 0.05  # K_Gly from Table 2.1
    beta_activity: float = 0.1  # Activity coefficient

    # Hormone production rates
    k_ghrelin: float = 0.05
    k_leptin: float = 0.05

    # Hormone degradation time constants
    tau_ghrelin: float = 20.0
    tau_leptin: float = 20.0

    # Leptin inhibition strength
    gamma_leptin: float = 1.0

    # Meal energy
    meal_intake: float = 10.0

    # Hunger threshold for deciding to seek food
    hunger_threshold: float = 0.4


@dataclass
class HomeostaticModel:
    params: HomeostaticParams = field(default_factory=HomeostaticParams)

    # State variables
    fat: float = field(init=False)
    glycogen: float = field(init=False)
    ghrelin: float = field(init=False)
    leptin: float = field(init=False)
    hunger: float = field(init=False)

    def __post_init__(self) -> None:
        self.fat = self.params.fat_init
        self.glycogen = self.params.glycogen_init
        self.ghrelin = self.params.ghrelin_init
        self.leptin = self.params.leptin_init
        self.hunger = self.params.hunger_init

    def _activity(self, step: int) -> float:
        """A(t) = 0.5 + 0.5 * e^(-t/100)"""
        return 0.5 + 0.5 * math.exp(-step / 100.0)

    def _step_odes(self, intake: float, step: int, dt: float = 1.0) -> None:
        p = self.params

        activity = self._activity(step)

        # dF/dt = cF * I - alphaF * F
        d_fat = p.c_fat * intake - p.alpha_fat * self.fat
        # dGly/dt = cGly * I - alphaGly * Gly - beta * A(t)
        d_glycogen = (
            p.c_glycogen * intake
            - p.alpha_glycogen * self.glycogen
            - p.beta_activity * activity
        )
        # dG/dt = kG * (1 - min(1, Gly/Glymax)) - G/tauG
        d_ghrelin = (
            p.k_ghrelin * (1.0 - min(1.0, self.glycogen / p.glycogen_max))
            - self.ghrelin / p.tau_ghrelin
        )
        # dL/dt = kL * min(1, F/Fmax) - L/tauL
        d_leptin = (
            p.k_leptin * min(1.0, self.fat / p.fat_max) - self.leptin / p.tau_leptin
        )

        self.fat = max(0.0, self.fat + d_fat * dt)
        self.glycogen = max(0.0, self.glycogen + d_glycogen * dt)
        self.ghrelin = max(0.0, self.ghrelin + d_ghrelin * dt)
        self.leptin = max(0.0, self.leptin + d_leptin * dt)

        # Leff = gamma * L * sigmoid(F/Fmax - 0.5)
        l_eff = p.gamma_leptin * self.leptin * _sigmoid(self.fat / p.fat_max - 0.5)
        # H = max(0, G - Leff)
        self.hunger = max(0.0, self.ghrelin - l_eff)

    def decide(self, perception: Perception) -> Action:
        if self.hunger > self.params.hunger_threshold and perception.food_sources:
            # Move toward closest food
            fx, fy = perception.food_sources[0]["x"], perception.food_sources[0]["y"]
            ax, ay = perception.position
            best_dist = abs(fx - ax) + abs(fy - ay)
            best_action = STAY
            for action_name, (dx, dy) in _DELTAS.items():
                nx, ny = ax + dx, ay + dy
                if (
                    0 <= nx < perception.grid_size[0]
                    and 0 <= ny < perception.grid_size[1]
                ):
                    dist = abs(fx - nx) + abs(fy - ny)
                    if dist < best_dist:
                        best_dist = dist
                        best_action = Action(action_name)
            return best_action
        return STAY

    def update(self, action: Action, reward: float, new_perception: Perception) -> None:
        intake = self.params.meal_intake if new_perception.ate_food else 0.0
        self._step_odes(intake, new_perception.step)

    def get_state(self) -> dict:
        return {
            "fat": self.fat,
            "glycogen": self.glycogen,
            "ghrelin": self.ghrelin,
            "leptin": self.leptin,
            "hunger": self.hunger,
        }


_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "stay": (0, 0),
}
