# tests/test_spec.py
from simlab.environment import ConsumeEffect, MoveEffect, NoopEffect
from simlab.spec import spec_to_environment, validate_spec_dict

VALID_SPEC = {
    "grid": {"width": 10, "height": 10},
    "actions": [
        {"name": "move_up", "effect": {"type": "MoveEffect", "dx": 0, "dy": -1}},
        {
            "name": "eat",
            "effect": {"type": "ConsumeEffect", "resource_type": "food", "reward": 1.0},
        },
    ],
    "resources": [
        {
            "type": "food",
            "properties": {"palatability": [0.1, 1.0]},
            "count": 5,
            "regenerate": True,
        },
    ],
}


# --- Task 1: Happy path ---


def test_valid_spec_returns_no_errors():
    errors = validate_spec_dict(VALID_SPEC)
    assert errors == []


# --- Task 2: Error cases ---


def test_missing_top_level_keys():
    errors = validate_spec_dict({})
    assert "Missing required key: 'grid'" in errors
    assert "Missing required key: 'actions'" in errors
    assert "Missing required key: 'resources'" in errors


def test_invalid_grid():
    spec = {**VALID_SPEC, "grid": {"width": -1, "height": 0}}
    errors = validate_spec_dict(spec)
    assert any("grid.width" in e for e in errors)
    assert any("grid.height" in e for e in errors)


def test_duplicate_action_names():
    spec = {
        **VALID_SPEC,
        "actions": [
            {"name": "eat", "effect": {"type": "NoopEffect"}},
            {"name": "eat", "effect": {"type": "NoopEffect"}},
        ],
    }
    errors = validate_spec_dict(spec)
    assert any("Duplicate action name" in e for e in errors)


def test_invalid_effect_type():
    spec = {
        **VALID_SPEC,
        "actions": [{"name": "fly", "effect": {"type": "FlyEffect"}}],
    }
    errors = validate_spec_dict(spec)
    assert any("FlyEffect" in e and "not valid" in e for e in errors)


def test_missing_effect_fields():
    spec = {
        **VALID_SPEC,
        "actions": [{"name": "eat", "effect": {"type": "ConsumeEffect"}}],
    }
    errors = validate_spec_dict(spec)
    assert any("resource_type" in e for e in errors)
    assert any("reward" in e for e in errors)


def test_duplicate_resource_types():
    spec = {
        **VALID_SPEC,
        "resources": [
            {"type": "food", "count": 3},
            {"type": "food", "count": 5},
        ],
    }
    errors = validate_spec_dict(spec)
    assert any("Duplicate resource type" in e for e in errors)


def test_consume_references_missing_resource():
    spec = {
        "grid": {"width": 10, "height": 10},
        "actions": [
            {
                "name": "drink",
                "effect": {
                    "type": "ConsumeEffect",
                    "resource_type": "water",
                    "reward": 1.0,
                },
            },
        ],
        "resources": [],
    }
    errors = validate_spec_dict(spec)
    assert any("water" in e and "not defined" in e for e in errors)


# --- Task 3: Conversion ---


def test_spec_to_environment_creates_correct_grid():
    env = spec_to_environment(VALID_SPEC, seed=42)
    assert env.width == 10
    assert env.height == 10


def test_spec_to_environment_registers_actions():
    env = spec_to_environment(VALID_SPEC, seed=42)
    assert "move_up" in env._action_registry
    assert "eat" in env._action_registry
    assert isinstance(env._action_registry["move_up"].effect, MoveEffect)
    assert isinstance(env._action_registry["eat"].effect, ConsumeEffect)


def test_spec_to_environment_spawns_resources():
    env = spec_to_environment(VALID_SPEC, seed=42)
    assert len(env._resources) == 5


def test_spec_to_environment_converts_ranges_to_tuples():
    env = spec_to_environment(VALID_SPEC, seed=42)
    rule = env._resource_rules["food"]
    assert isinstance(rule.properties["palatability"], tuple)
    assert rule.properties["palatability"] == (0.1, 1.0)


def test_spec_to_environment_noop_effect():
    spec = {
        "grid": {"width": 5, "height": 5},
        "actions": [{"name": "rest", "effect": {"type": "NoopEffect", "reward": 0.5}}],
        "resources": [],
    }
    env = spec_to_environment(spec, seed=1)
    assert isinstance(env._action_registry["rest"].effect, NoopEffect)
    assert env._action_registry["rest"].effect.reward == 0.5
