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
