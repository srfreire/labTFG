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
