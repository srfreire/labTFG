"""Integrated model — combines homeostatic + hedonic with 4 integration modes.

From Denis TFM section 2.4:
  Case 1: Independent — signals averaged
  Case 2: Hedonic -> Homeostatic — H(t) = 0.95*H(t) + 0.05*W(t)
  Case 3.1: Homeostatic -> Hedonic (immediate) — R(t) = R(t) * H(t)/Hm
  Case 3.2: Homeostatic -> Hedonic (expected) — Qmax(t) = Qmax(t) * H(t)/Hm
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from decisionlab.models.protocol import Action, Perception
from denis.hedonic import HedonicModel
from denis.homeostatic import HomeostaticModel


class IntegrationMode(Enum):
    INDEPENDENT = "independent"
    HEDONIC_TO_HOMEOSTATIC = "hedonic_to_homeostatic"
    HOMEOSTATIC_TO_HEDONIC_IMMEDIATE = "homeostatic_to_hedonic_immediate"
    HOMEOSTATIC_TO_HEDONIC_EXPECTED = "homeostatic_to_hedonic_expected"


@dataclass
class IntegratedModel:
    homeostatic: HomeostaticModel
    hedonic: HedonicModel
    mode: IntegrationMode = IntegrationMode.INDEPENDENT

    _hunger_mean: float = field(init=False, default=0.5)
    _hunger_history_sum: float = field(init=False, default=0.5)
    _hunger_history_count: int = field(init=False, default=1)
    _last_position: tuple[int, int] = field(init=False, default=(0, 0))
    _last_food_sources: list[dict] = field(init=False, default_factory=list)

    def decide(self, perception: Perception) -> Action:
        return self.hedonic.decide(perception)

    def update(self, action: Action, reward: float, new_perception: Perception) -> None:
        self._last_position = new_perception.position
        self._last_food_sources = new_perception.food_sources

        # 1. Update homeostatic physiology
        self.homeostatic.update(action, reward, new_perception)
        hunger = self.homeostatic.hunger
        hedonic_sig = self.hedonic.hedonic_signal(
            new_perception.position, new_perception.food_sources
        )

        # Track running mean of hunger for Hm
        self._hunger_history_sum += hunger
        self._hunger_history_count += 1
        self._hunger_mean = self._hunger_history_sum / self._hunger_history_count

        # 2. Apply integration mode
        effective_reward = reward

        if self.mode == IntegrationMode.HEDONIC_TO_HOMEOSTATIC:
            # Case 2: H(t) = 0.95*H(t) + 0.05*W(t)
            self.homeostatic.hunger = 0.95 * hunger + 0.05 * hedonic_sig

        elif self.mode == IntegrationMode.HOMEOSTATIC_TO_HEDONIC_IMMEDIATE:
            # Case 3.1: R(t) = R(t) * H(t)/Hm
            if self._hunger_mean > 0:
                effective_reward = reward * (hunger / self._hunger_mean)

        elif self.mode == IntegrationMode.HOMEOSTATIC_TO_HEDONIC_EXPECTED:  # noqa: SIM102
            # Case 3.2: Qmax(t) = Qmax(t) * H(t)/Hm
            # Scaling gamma by H/Hm is equivalent to scaling Qmax in the TD target
            if self._hunger_mean > 0:
                ratio = hunger / self._hunger_mean
                saved_gamma = self.hedonic.params.discount_factor
                self.hedonic.params.discount_factor = saved_gamma * ratio
                self.hedonic.update(action, reward, new_perception)
                self.hedonic.params.discount_factor = saved_gamma
                return

        # 3. Update hedonic model with (possibly modulated) reward
        self.hedonic.update(action, effective_reward, new_perception)

    def get_state(self) -> dict:
        return {
            "homeostatic": self.homeostatic.get_state(),
            "hedonic": {"epsilon": self.hedonic.epsilon},
            "hunger_signal": self.homeostatic.hunger,
            "hedonic_signal": self.hedonic.hedonic_signal(
                self._last_position, self._last_food_sources
            ),
            "mode": self.mode.value,
        }
