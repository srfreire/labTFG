from decisionlab.models.protocol import Action, Perception, DecisionModel, UP, DOWN, LEFT, RIGHT, STAY


def test_action_dataclass():
    a = Action("up")
    assert a.name == "up"
    assert a.params == {}


def test_action_with_params():
    a = Action("move", {"direction": "up"})
    assert a.name == "move"
    assert a.params == {"direction": "up"}


def test_action_constants():
    assert UP.name == "up"
    assert DOWN.name == "down"
    assert LEFT.name == "left"
    assert RIGHT.name == "right"
    assert STAY.name == "stay"


def test_perception_creation():
    p = Perception(
        position=(2, 3),
        grid_size=(5, 5),
        food_sources=({"x": 1, "y": 1, "palatability": 0.8},),
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
            return STAY

        def update(self, action: Action, reward: float, new_perception: Perception) -> None:
            pass

        def get_state(self) -> dict:
            return {}

    model: DecisionModel = DummyModel()
    p = Perception(position=(0, 0), grid_size=(5, 5), food_sources=(), ate_food=False, step=0)
    assert model.decide(p) == STAY
    assert model.get_state() == {}
