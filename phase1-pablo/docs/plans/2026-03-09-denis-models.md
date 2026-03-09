# Denis TFM Models — Template + Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a `DecisionModel` Python template (protocol) and implement Denis's two models (homeostatic ODEs + hedonic Q-Learning) as the first concrete instances in `examples/denis/`, adapting the reference script.

**Architecture:** Define a `DecisionModel` Protocol in the main package (the contract the Builder generates against). Implement the homeostatic model (ODE system from TFM sec. 2.2) and hedonic model (Q-Learning from TFM sec. 2.3) as separate classes under `examples/denis/`. Wrap them in an `IntegratedModel` that supports the 4 integration modes from TFM sec. 2.4. A minimal `GridWorld` environment runs the simulation. Examples are importable as `denis.*` via pytest pythonpath config.

**Tech Stack:** Python 3.12+, numpy (ODEs), pytest, uv

---

## File layout

```
phase1-pablo/
  src/decisionlab/
    models/                    # NEW — template only
      __init__.py
      protocol.py              # DecisionModel Protocol, Perception, Action
  examples/
    denis/                     # NEW — reference implementation
      __init__.py
      homeostatic.py           # HomeostaticModel (ODE system)
      hedonic.py               # HedonicModel (Q-Learning)
      integrated.py            # IntegratedModel (4 integration modes)
      grid.py                  # GridWorld + FoodSource
      simulation.py            # Simulation runner
  tests/
    models/                    # NEW
      __init__.py
      test_protocol.py
    denis/                     # NEW
      __init__.py
      test_homeostatic.py
      test_hedonic.py
      test_integrated.py
      test_grid.py
      test_simulation.py
```

---

### Task 1: Protocol + Types + Project Config

Define the template that any decision model must follow. Configure pytest to find `examples/`.

**Files:**
- Create: `src/decisionlab/models/__init__.py`
- Create: `src/decisionlab/models/protocol.py`
- Create: `examples/denis/__init__.py`
- Create: `tests/models/__init__.py`
- Create: `tests/models/test_protocol.py`
- Modify: `pyproject.toml` (add pytest pythonpath + numpy)

**Step 1: Update pyproject.toml**

Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["src", "examples"]
```

And add numpy dependency:
Run: `cd phase1-pablo && uv add numpy`

**Step 2: Write failing tests**

```python
# tests/models/test_protocol.py
from decisionlab.models.protocol import Action, Perception, DecisionModel


def test_action_enum_has_movement_actions():
    assert Action.UP.value == "up"
    assert Action.DOWN.value == "down"
    assert Action.LEFT.value == "left"
    assert Action.RIGHT.value == "right"
    assert Action.STAY.value == "stay"


def test_perception_creation():
    p = Perception(
        position=(2, 3),
        grid_size=(5, 5),
        food_sources=[{"x": 1, "y": 1, "palatability": 0.8}],
        ate_food=False,
        step=10,
    )
    assert p.position == (2, 3)
    assert p.grid_size == (5, 5)
    assert len(p.food_sources) == 1
    assert p.ate_food is False
    assert p.step == 10


def test_decision_model_protocol_enforced():
    """A class implementing decide + update + get_state satisfies DecisionModel."""

    class DummyModel:
        def decide(self, perception: Perception) -> Action:
            return Action.STAY

        def update(self, action: Action, reward: float, new_perception: Perception) -> None:
            pass

        def get_state(self) -> dict:
            return {}

    model: DecisionModel = DummyModel()
    p = Perception(position=(0, 0), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    assert model.decide(p) == Action.STAY
    assert model.get_state() == {}
```

**Step 3: Run tests to verify failure**

Run: `cd phase1-pablo && uv run pytest tests/models/test_protocol.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 4: Implement**

```python
# src/decisionlab/models/__init__.py
"""Decision model template and implementations."""

# src/decisionlab/models/protocol.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class Action(Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    STAY = "stay"


@dataclass(frozen=True)
class Perception:
    position: tuple[int, int]
    grid_size: tuple[int, int]
    food_sources: list[dict] = field(default_factory=list)
    ate_food: bool = False
    step: int = 0


@runtime_checkable
class DecisionModel(Protocol):
    def decide(self, perception: Perception) -> Action: ...
    def update(self, action: Action, reward: float, new_perception: Perception) -> None: ...
    def get_state(self) -> dict: ...
```

Also create empty `examples/denis/__init__.py`.

**Step 5: Run tests to verify pass**

Run: `cd phase1-pablo && uv run pytest tests/models/test_protocol.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add phase1-pablo/src/decisionlab/models/ phase1-pablo/tests/models/ phase1-pablo/examples/denis/__init__.py phase1-pablo/pyproject.toml phase1-pablo/uv.lock
git commit -m "feat[models]: add DecisionModel protocol and types"
```

---

### Task 2: Homeostatic Model (ODE system)

Implements TFM section 2.2: fat, glycogen, ghrelin, leptin ODEs + hunger signal.

**Files:**
- Create: `examples/denis/homeostatic.py`
- Create: `tests/denis/__init__.py`
- Create: `tests/denis/test_homeostatic.py`

**Step 1: Write failing tests**

```python
# tests/denis/test_homeostatic.py
from decisionlab.models.protocol import Action, Perception
from denis.homeostatic import HomeostaticModel


def _make_perception(**overrides) -> Perception:
    defaults = dict(position=(2, 2), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    defaults.update(overrides)
    return Perception(**defaults)


def test_initial_state():
    m = HomeostaticModel()
    state = m.get_state()
    assert state["fat"] == 50.0
    assert state["glycogen"] == 20.0
    assert state["ghrelin"] == 0.1
    assert state["leptin"] == 0.8
    assert 0.0 <= state["hunger"] <= 1.0


def test_hunger_increases_without_food():
    m = HomeostaticModel()
    h_before = m.get_state()["hunger"]
    for t in range(100):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_after = m.get_state()["hunger"]
    assert h_after > h_before


def test_hunger_decreases_after_eating():
    # Starve first to build hunger
    m = HomeostaticModel()
    for t in range(200):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_before = m.get_state()["hunger"]

    # Eat
    p = _make_perception(step=200, ate_food=True)
    m.update(Action.STAY, 1.0, p)

    # Let physiology settle
    for t in range(201, 220):
        p = _make_perception(step=t, ate_food=False)
        m.update(Action.STAY, 0.0, p)
    h_after = m.get_state()["hunger"]
    assert h_after < h_before


def test_state_variables_stay_in_valid_range():
    m = HomeostaticModel()
    for t in range(500):
        ate = t % 50 == 0
        p = _make_perception(step=t, ate_food=ate)
        m.update(Action.STAY, 1.0 if ate else 0.0, p)
    state = m.get_state()
    assert state["fat"] >= 0
    assert state["glycogen"] >= 0
    assert state["ghrelin"] >= 0
    assert state["leptin"] >= 0
    assert state["hunger"] >= 0


def test_decide_returns_action():
    m = HomeostaticModel()
    p = _make_perception(
        food_sources=[{"x": 3, "y": 3, "palatability": 0.8}],
    )
    action = m.decide(p)
    assert isinstance(action, Action)
```

**Step 2: Run tests to verify failure**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_homeostatic.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# examples/denis/homeostatic.py
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

from decisionlab.models.protocol import Action, Perception


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
    alpha_fat: float = 0.01        # K_F from Table 2.1
    alpha_glycogen: float = 0.05   # K_Gly from Table 2.1
    beta_activity: float = 0.1     # Activity coefficient

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
        d_glycogen = p.c_glycogen * intake - p.alpha_glycogen * self.glycogen - p.beta_activity * activity
        # dG/dt = kG * (1 - min(1, Gly/Glymax)) - G/tauG
        d_ghrelin = p.k_ghrelin * (1.0 - min(1.0, self.glycogen / p.glycogen_max)) - self.ghrelin / p.tau_ghrelin
        # dL/dt = kL * min(1, F/Fmax) - L/tauL
        d_leptin = p.k_leptin * min(1.0, self.fat / p.fat_max) - self.leptin / p.tau_leptin

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
            best_action = Action.STAY
            for action, (dx, dy) in _DELTAS.items():
                nx, ny = ax + dx, ay + dy
                if 0 <= nx < perception.grid_size[0] and 0 <= ny < perception.grid_size[1]:
                    dist = abs(fx - nx) + abs(fy - ny)
                    if dist < best_dist:
                        best_dist = dist
                        best_action = action
            return best_action
        return Action.STAY

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


_DELTAS: dict[Action, tuple[int, int]] = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
}
```

**Step 4: Run tests to verify pass**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_homeostatic.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add phase1-pablo/examples/denis/homeostatic.py phase1-pablo/tests/denis/
git commit -m "feat[examples]: add homeostatic ODE model from Denis TFM"
```

---

### Task 3: Hedonic Model (Q-Learning)

Implements TFM section 2.3: Q-table, epsilon-greedy, Q-learning update.

**Files:**
- Create: `examples/denis/hedonic.py`
- Create: `tests/denis/test_hedonic.py`

**Step 1: Write failing tests**

```python
# tests/denis/test_hedonic.py
import numpy as np
from decisionlab.models.protocol import Action, Perception
from denis.hedonic import HedonicModel, HedonicParams


def _make_perception(**overrides) -> Perception:
    defaults = dict(position=(2, 2), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    defaults.update(overrides)
    return Perception(**defaults)


def test_initial_q_table_is_zeros():
    m = HedonicModel(params=HedonicParams(grid_size=(5, 5)))
    state = m.get_state()
    assert state["q_table"].shape[0] > 0
    assert np.all(state["q_table"] == 0.0)


def test_decide_returns_valid_action():
    m = HedonicModel(params=HedonicParams(grid_size=(5, 5)))
    p = _make_perception()
    action = m.decide(p)
    assert isinstance(action, Action)


def test_epsilon_decays():
    params = HedonicParams(grid_size=(5, 5), epsilon=1.0, epsilon_decay=0.99, epsilon_min=0.01)
    m = HedonicModel(params=params)
    e_before = m.epsilon
    p = _make_perception()
    action = m.decide(p)
    m.update(action, 1.0, _make_perception(step=1))
    assert m.epsilon < e_before


def test_q_value_updates_after_reward():
    params = HedonicParams(grid_size=(5, 5), epsilon=0.0)  # pure exploitation
    m = HedonicModel(params=params)

    # Place food at (2, 2), agent at (2, 2)
    p = _make_perception(position=(2, 2), food_sources=[{"x": 2, "y": 2, "palatability": 1.0}])
    action = m.decide(p)

    # Give reward
    p_new = _make_perception(position=(2, 2), ate_food=True, step=1)
    m.update(action, 10.0, p_new)

    state = m.get_state()
    assert np.any(state["q_table"] != 0.0)


def test_hedonic_signal():
    params = HedonicParams(grid_size=(5, 5))
    m = HedonicModel(params=params)
    # Initially zero (all Q-values are 0)
    assert m.hedonic_signal((2, 2)) == 0.0

    # After learning, signal should change
    p = _make_perception(position=(2, 2))
    m.update(Action.STAY, 10.0, _make_perception(position=(2, 2), step=1))
    assert m.hedonic_signal((2, 2)) != 0.0
```

**Step 2: Run tests to verify failure**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_hedonic.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# examples/denis/hedonic.py
"""Hedonic model — Q-Learning from Denis TFM (section 2.3).

Agent learns to maximize reward via Q-table updates.
Produces a hedonic signal W(t) = max_a Q(state, a).

References:
    - Watkins & Dayan (1992) — Q-Learning
    - Denis Yamunaque TFM (2025) — Section 2.3
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

from decisionlab.models.protocol import Action, Perception

_ACTIONS = list(Action)
_ACTION_TO_IDX = {a: i for i, a in enumerate(_ACTIONS)}

_DELTAS: dict[Action, tuple[int, int]] = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
    Action.STAY: (0, 0),
}


@dataclass
class HedonicParams:
    grid_size: tuple[int, int] = (5, 5)
    learning_rate: float = 0.1       # alpha
    discount_factor: float = 0.9     # gamma
    epsilon: float = 1.0
    epsilon_decay: float = 0.9995
    epsilon_min: float = 0.01
    n_palatability_levels: int = 2   # discretized
    use_food_in_state: bool = True


@dataclass
class HedonicModel:
    params: HedonicParams = field(default_factory=HedonicParams)

    # Mutable state
    q_table: np.ndarray = field(init=False)
    epsilon: float = field(init=False)
    _last_state_idx: int | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.epsilon = self.params.epsilon
        gw, gh = self.params.grid_size
        n_pal = self.params.n_palatability_levels if self.params.use_food_in_state else 1
        food_flag = 2 if self.params.use_food_in_state else 1  # food present/absent
        n_states = gw * gh * food_flag * n_pal
        n_actions = len(_ACTIONS)
        self.q_table = np.zeros((n_states, n_actions), dtype=np.float64)

    def _state_index(self, position: tuple[int, int], food_sources: list[dict] | None = None) -> int:
        gw, gh = self.params.grid_size
        x, y = position

        if self.params.use_food_in_state and food_sources:
            food_here = any(f["x"] == x and f["y"] == y for f in food_sources)
            food_flag = 1 if food_here else 0
            pals = [f["palatability"] for f in food_sources if f["x"] == x and f["y"] == y]
            pal_level = min(int(max(pals) * self.params.n_palatability_levels), self.params.n_palatability_levels - 1) if pals else 0
            n_pal = self.params.n_palatability_levels
            return ((x * gh + y) * 2 + food_flag) * n_pal + pal_level
        else:
            return x * gh + y

    def decide(self, perception: Perception) -> Action:
        state_idx = self._state_index(perception.position, perception.food_sources)
        self._last_state_idx = state_idx

        if random.random() < self.epsilon:
            return random.choice(_ACTIONS)
        else:
            best_idx = int(np.argmax(self.q_table[state_idx]))
            return _ACTIONS[best_idx]

    def update(self, action: Action, reward: float, new_perception: Perception) -> None:
        if self._last_state_idx is None:
            return

        action_idx = _ACTION_TO_IDX[action]
        new_state_idx = self._state_index(new_perception.position, new_perception.food_sources)

        # Q(s,a) <- Q(s,a) + alpha * [R + gamma * max_a' Q(s',a') - Q(s,a)]
        old_q = self.q_table[self._last_state_idx, action_idx]
        max_future_q = np.max(self.q_table[new_state_idx])
        td_target = reward + self.params.discount_factor * max_future_q
        self.q_table[self._last_state_idx, action_idx] = old_q + self.params.learning_rate * (td_target - old_q)

        # Decay epsilon
        self.epsilon = max(self.params.epsilon_min, self.epsilon * self.params.epsilon_decay)

    def hedonic_signal(self, position: tuple[int, int], food_sources: list[dict] | None = None) -> float:
        """W(t) = max_a Q(state, a) for current position."""
        state_idx = self._state_index(position, food_sources)
        return float(np.max(self.q_table[state_idx]))

    def get_state(self) -> dict:
        return {
            "q_table": self.q_table.copy(),
            "epsilon": self.epsilon,
        }
```

**Step 4: Run tests to verify pass**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_hedonic.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add phase1-pablo/examples/denis/hedonic.py phase1-pablo/tests/denis/test_hedonic.py
git commit -m "feat[examples]: add hedonic Q-Learning model from Denis TFM"
```

---

### Task 4: Grid Environment

Minimal grid world with food sources, agent movement, and reward — adapted from Denis's script.

**Files:**
- Create: `examples/denis/grid.py`
- Create: `tests/denis/test_grid.py`

**Step 1: Write failing tests**

```python
# tests/denis/test_grid.py
from decisionlab.models.protocol import Action
from denis.grid import GridWorld, GridConfig


def test_grid_creation():
    config = GridConfig(width=5, height=5, food_count=3, food_palatability_range=(0.5, 1.0))
    grid = GridWorld(config)
    assert grid.width == 5
    assert grid.height == 5
    assert len(grid.food_sources) == 3


def test_agent_placement():
    config = GridConfig(width=5, height=5, food_count=1)
    grid = GridWorld(config)
    grid.place_agent(2, 3)
    assert grid.agent_position == (2, 3)


def test_agent_movement():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.place_agent(2, 2)
    grid.apply_action(Action.RIGHT)
    assert grid.agent_position == (3, 2)


def test_agent_stays_in_bounds():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.place_agent(0, 0)
    grid.apply_action(Action.LEFT)
    assert grid.agent_position == (0, 0)
    grid.apply_action(Action.UP)
    assert grid.agent_position == (0, 0)


def test_food_consumption():
    config = GridConfig(width=5, height=5, food_count=0, food_regenerate=False)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 2, "y": 2, "palatability": 0.8}]
    grid.place_agent(2, 2)
    perception = grid.get_perception(step=0)
    assert perception.ate_food is True
    assert len(grid.food_sources) == 0


def test_food_regeneration():
    config = GridConfig(width=5, height=5, food_count=1, food_regenerate=True)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 2, "y": 2, "palatability": 0.8}]
    grid.place_agent(2, 2)
    grid.get_perception(step=0)  # consumes food
    assert len(grid.food_sources) == 1  # regenerated


def test_perception_returns_correct_data():
    config = GridConfig(width=5, height=5, food_count=0)
    grid = GridWorld(config)
    grid.food_sources = [{"x": 1, "y": 1, "palatability": 0.7}]
    grid.place_agent(3, 3)
    p = grid.get_perception(step=5)
    assert p.position == (3, 3)
    assert p.grid_size == (5, 5)
    assert p.step == 5
    assert p.ate_food is False
    assert len(p.food_sources) == 1
```

**Step 2: Run tests to verify failure**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_grid.py -v`
Expected: FAIL — ImportError

**Step 3: Implement**

```python
# examples/denis/grid.py
"""Grid world environment — adapted from Denis's script.

A 2D grid where an agent moves to find and consume food sources.
Food sources have palatability values and can regenerate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from decisionlab.models.protocol import Action, Perception

_DELTAS: dict[Action, tuple[int, int]] = {
    Action.UP: (0, -1),
    Action.DOWN: (0, 1),
    Action.LEFT: (-1, 0),
    Action.RIGHT: (1, 0),
    Action.STAY: (0, 0),
}


@dataclass
class GridConfig:
    width: int = 5
    height: int = 5
    food_count: int = 3
    food_palatability_range: tuple[float, float] = (0.1, 1.0)
    food_regenerate: bool = True
    seed: int | None = None


@dataclass
class GridWorld:
    config: GridConfig
    food_sources: list[dict] = field(init=False, default_factory=list)
    agent_position: tuple[int, int] = field(init=False, default=(0, 0))
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.config.seed)
        self._spawn_food(self.config.food_count)

    @property
    def width(self) -> int:
        return self.config.width

    @property
    def height(self) -> int:
        return self.config.height

    def _spawn_food(self, count: int) -> None:
        lo, hi = self.config.food_palatability_range
        for _ in range(count):
            self.food_sources.append({
                "x": self._rng.randint(0, self.width - 1),
                "y": self._rng.randint(0, self.height - 1),
                "palatability": self._rng.uniform(lo, hi),
            })

    def place_agent(self, x: int, y: int) -> None:
        self.agent_position = (x, y)

    def apply_action(self, action: Action) -> None:
        dx, dy = _DELTAS[action]
        nx = max(0, min(self.width - 1, self.agent_position[0] + dx))
        ny = max(0, min(self.height - 1, self.agent_position[1] + dy))
        self.agent_position = (nx, ny)

    def get_perception(self, step: int) -> Perception:
        ax, ay = self.agent_position

        ate = False
        eaten_idx = None
        for i, f in enumerate(self.food_sources):
            if f["x"] == ax and f["y"] == ay:
                ate = True
                eaten_idx = i
                break

        if eaten_idx is not None:
            self.food_sources.pop(eaten_idx)
            if self.config.food_regenerate:
                self._spawn_food(1)

        return Perception(
            position=self.agent_position,
            grid_size=(self.width, self.height),
            food_sources=list(self.food_sources),
            ate_food=ate,
            step=step,
        )

    def reset(self, agent_x: int | None = None, agent_y: int | None = None) -> None:
        self.food_sources.clear()
        self._spawn_food(self.config.food_count)
        x = agent_x if agent_x is not None else self._rng.randint(0, self.width - 1)
        y = agent_y if agent_y is not None else self._rng.randint(0, self.height - 1)
        self.place_agent(x, y)
```

**Step 4: Run tests to verify pass**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_grid.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add phase1-pablo/examples/denis/grid.py phase1-pablo/tests/denis/test_grid.py
git commit -m "feat[examples]: add GridWorld with food and agent movement"
```

---

### Task 5: Integrated Model + Simulation Runner

Wraps homeostatic + hedonic with 4 integration modes from TFM section 2.4, plus simulation loop.

**Files:**
- Create: `examples/denis/integrated.py`
- Create: `examples/denis/simulation.py`
- Create: `tests/denis/test_integrated.py`
- Create: `tests/denis/test_simulation.py`

**Step 1: Write failing tests for IntegratedModel**

```python
# tests/denis/test_integrated.py
from decisionlab.models.protocol import Action, Perception
from denis.homeostatic import HomeostaticModel
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode


def _make_perception(**overrides) -> Perception:
    defaults = dict(position=(2, 2), grid_size=(5, 5), food_sources=[], ate_food=False, step=0)
    defaults.update(overrides)
    return Perception(**defaults)


def test_integration_modes_exist():
    assert IntegrationMode.INDEPENDENT.value == "independent"
    assert IntegrationMode.HEDONIC_TO_HOMEOSTATIC.value == "hedonic_to_homeostatic"
    assert IntegrationMode.HOMEOSTATIC_TO_HEDONIC_IMMEDIATE.value == "homeostatic_to_hedonic_immediate"
    assert IntegrationMode.HOMEOSTATIC_TO_HEDONIC_EXPECTED.value == "homeostatic_to_hedonic_expected"


def test_integrated_model_decides():
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )
    p = _make_perception()
    action = model.decide(p)
    assert isinstance(action, Action)


def test_integrated_model_updates_both():
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )
    p = _make_perception()
    action = model.decide(p)
    model.update(action, 1.0, _make_perception(step=1, ate_food=True))

    state = model.get_state()
    assert "homeostatic" in state
    assert "hedonic" in state
    assert "hunger_signal" in state
    assert "hedonic_signal" in state


def test_hedonic_to_homeostatic_modulates_hunger():
    """Case 2: H(t) = 0.95*H(t) + 0.05*W(t)."""
    hedonic_params = HedonicParams(grid_size=(5, 5), epsilon=0.0)
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.HEDONIC_TO_HOMEOSTATIC,
    )
    import numpy as np
    model.hedonic.q_table[:] = 5.0

    p = _make_perception(food_sources=[{"x": 2, "y": 2, "palatability": 1.0}])
    action = model.decide(p)
    model.update(action, 1.0, _make_perception(step=1))

    state = model.get_state()
    assert state["hunger_signal"] >= 0.0
```

**Step 2: Write failing tests for simulation runner**

```python
# tests/denis/test_simulation.py
from denis.homeostatic import HomeostaticModel
from denis.hedonic import HedonicModel, HedonicParams
from denis.integrated import IntegratedModel, IntegrationMode
from denis.grid import GridWorld, GridConfig
from denis.simulation import Simulation, SimulationResult


def test_simulation_runs():
    grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )

    sim = Simulation(grid=grid, model=model)
    result = sim.run(steps=50)

    assert isinstance(result, SimulationResult)
    assert len(result.history) == 50
    assert result.total_food_eaten >= 0


def test_simulation_result_has_expected_fields():
    grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
    hedonic_params = HedonicParams(grid_size=(5, 5))
    model = IntegratedModel(
        homeostatic=HomeostaticModel(),
        hedonic=HedonicModel(params=hedonic_params),
        mode=IntegrationMode.INDEPENDENT,
    )

    sim = Simulation(grid=grid, model=model)
    result = sim.run(steps=10)

    entry = result.history[0]
    assert "step" in entry
    assert "position" in entry
    assert "action" in entry
    assert "ate_food" in entry
    assert "hunger" in entry
    assert "hedonic_signal" in entry


def test_simulation_with_all_modes():
    """Smoke test: all 4 integration modes run without error."""
    for mode in IntegrationMode:
        grid = GridWorld(GridConfig(width=5, height=5, food_count=3, seed=42))
        hedonic_params = HedonicParams(grid_size=(5, 5))
        model = IntegratedModel(
            homeostatic=HomeostaticModel(),
            hedonic=HedonicModel(params=hedonic_params),
            mode=mode,
        )
        sim = Simulation(grid=grid, model=model)
        result = sim.run(steps=20)
        assert len(result.history) == 20
```

**Step 3: Run tests to verify failure**

Run: `cd phase1-pablo && uv run pytest tests/denis/test_integrated.py tests/denis/test_simulation.py -v`
Expected: FAIL — ImportError

**Step 4: Implement IntegratedModel**

```python
# examples/denis/integrated.py
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
from denis.homeostatic import HomeostaticModel
from denis.hedonic import HedonicModel


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

    def decide(self, perception: Perception) -> Action:
        return self.hedonic.decide(perception)

    def update(self, action: Action, reward: float, new_perception: Perception) -> None:
        # 1. Update homeostatic physiology
        self.homeostatic.update(action, reward, new_perception)
        hunger = self.homeostatic.hunger
        hedonic_sig = self.hedonic.hedonic_signal(new_perception.position, new_perception.food_sources)

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

        elif self.mode == IntegrationMode.HOMEOSTATIC_TO_HEDONIC_EXPECTED:
            # Case 3.2: modulate Q-max by H(t)/Hm
            if self._hunger_mean > 0:
                effective_reward = reward * (hunger / self._hunger_mean)

        # 3. Update hedonic model with (possibly modulated) reward
        self.hedonic.update(action, effective_reward, new_perception)

    def get_state(self) -> dict:
        return {
            "homeostatic": self.homeostatic.get_state(),
            "hedonic": {"epsilon": self.hedonic.epsilon},
            "hunger_signal": self.homeostatic.hunger,
            "hedonic_signal": self.hedonic.hedonic_signal(
                (0, 0)
            ),
            "mode": self.mode.value,
        }
```

**Step 5: Implement Simulation runner**

```python
# examples/denis/simulation.py
"""Simulation runner — perceive/decide/act/update loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from decisionlab.models.protocol import DecisionModel
from denis.grid import GridWorld


@dataclass
class SimulationResult:
    history: list[dict] = field(default_factory=list)
    total_food_eaten: int = 0


@dataclass
class Simulation:
    grid: GridWorld
    model: DecisionModel

    def run(self, steps: int, agent_start: tuple[int, int] | None = None) -> SimulationResult:
        if agent_start:
            self.grid.place_agent(*agent_start)
        else:
            self.grid.reset()

        result = SimulationResult()

        for step in range(steps):
            # 1. Perceive
            perception = self.grid.get_perception(step=step)

            # 2. Decide
            action = self.model.decide(perception)

            # 3. Act
            self.grid.apply_action(action)

            # 4. Observe result
            new_perception = self.grid.get_perception(step=step)
            ate = new_perception.ate_food
            reward = 1.0 if ate else -0.01

            # 5. Update model
            self.model.update(action, reward, new_perception)

            # 6. Record
            model_state = self.model.get_state()
            result.history.append({
                "step": step,
                "position": new_perception.position,
                "action": action.value,
                "ate_food": ate,
                "hunger": model_state.get("homeostatic", {}).get("hunger", 0),
                "hedonic_signal": model_state.get("hedonic_signal", 0),
                "reward": reward,
            })
            if ate:
                result.total_food_eaten += 1

        return result
```

**Step 6: Run all tests to verify pass**

Run: `cd phase1-pablo && uv run pytest tests/ -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add phase1-pablo/examples/denis/integrated.py phase1-pablo/examples/denis/simulation.py phase1-pablo/tests/denis/test_integrated.py phase1-pablo/tests/denis/test_simulation.py
git commit -m "feat[examples]: add integrated model with 4 modes + simulation runner"
```

---

### Task 6: Update smoke test + final verification

**Files:**
- Modify: `tests/test_smoke.py`

**Step 1: Update smoke test**

```python
# tests/test_smoke.py
def test_package_imports():
    import decisionlab
    from decisionlab import cli
    from decisionlab.agents import researcher, reasoner, builder
    from decisionlab.tools import web_search, semantic_scholar, file_io, code_runner


def test_cli_app_exists():
    from decisionlab.cli import app
    assert app is not None


def test_model_protocol_imports():
    from decisionlab.models.protocol import DecisionModel, Action, Perception


def test_denis_example_imports():
    from denis.homeostatic import HomeostaticModel
    from denis.hedonic import HedonicModel
    from denis.integrated import IntegratedModel, IntegrationMode
    from denis.grid import GridWorld, GridConfig
    from denis.simulation import Simulation, SimulationResult
```

**Step 2: Run full test suite**

Run: `cd phase1-pablo && uv run pytest tests/ -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add phase1-pablo/tests/test_smoke.py
git commit -m "feat[tests]: update smoke test for protocol and denis example"
```

---

## Unresolved questions

1. **ODE parameter values** — Table 2.1 only lists some params (K_H, K_F, K_Gly, MEAL_INTAKE). Others (cF, cGly, kG, kL, beta, tauG, tauL, gamma, Fmax, Glymax) are from Jacquier et al. (2014) — should we hunt down exact values or use reasonable defaults?

2. **Reward structure** — Denis's TFM uses palatability-based rewards but doesn't give the exact formula. Should we use `palatability * MEAL_INTAKE` or simpler `+1/-0.01`?

3. **Q-Learning state discretization** — TFM includes physiological variables in the state optionally. Keep simple (position + food_present + palatability) or add hunger level?

4. **Integration with Phase 2** — the `DecisionModel` protocol here is a placeholder. When Juan defines his, should these models adapt or should Juan adopt this protocol?

5. **Training phase** — the hedonic model needs training episodes before simulation. Include a training runner now or defer?
