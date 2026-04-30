"""
Spec validation and conversion.

An environment spec is a JSON dict that describes a simulation:
  - grid: dimensions (width × height)
  - actions: what agents can do (move, eat, rest...)
  - resources: what exists in the world (food, water...)

This module validates specs and converts them into Environment objects.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_EFFECT_TYPES = {"MoveEffect", "ConsumeEffect", "NoopEffect"}

REQUIRED_EFFECT_FIELDS: dict[str, list[str]] = {
    "MoveEffect": ["dx", "dy"],
    "ConsumeEffect": ["resource_type", "reward"],
    "NoopEffect": [],
}


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


def validate_spec_dict(spec: dict) -> list[str]:
    """Validate an environment spec dict.

    Returns a list of error strings. Empty list = valid spec.
    Checks: required keys, types, uniqueness, and cross-references.
    """
    errors: list[str] = []

    # 1. Top-level required keys
    for key in ("grid", "actions", "resources"):
        if key not in spec:
            errors.append(f"Missing required key: '{key}'")
    if errors:
        return errors

    # 2. Grid dimensions
    grid = spec["grid"]
    if not isinstance(grid.get("width"), int) or grid["width"] <= 0:
        errors.append("grid.width must be a positive integer")
    if not isinstance(grid.get("height"), int) or grid["height"] <= 0:
        errors.append("grid.height must be a positive integer")

    # 3. Actions — must be non-empty, unique names, valid effects
    actions = spec["actions"]
    if not isinstance(actions, list) or len(actions) == 0:
        errors.append("actions must be a non-empty list")
        return errors

    action_names: list[str] = []
    for i, action in enumerate(actions):
        name = action.get("name")
        if not isinstance(name, str):
            errors.append(f"actions[{i}].name must be a string")
            continue
        if name in action_names:
            errors.append(f"Duplicate action name: '{name}'")
        action_names.append(name)

        effect = action.get("effect")
        if not isinstance(effect, dict):
            errors.append(f"actions[{i}].effect must be an object")
            continue
        etype = effect.get("type")
        if etype not in VALID_EFFECT_TYPES:
            errors.append(
                f"actions[{i}].effect.type '{etype}' is not valid. Must be one of {VALID_EFFECT_TYPES}"
            )
            continue
        for field in REQUIRED_EFFECT_FIELDS[etype]:
            if field not in effect:
                errors.append(
                    f"actions[{i}].effect missing required field '{field}' for {etype}"
                )

    # 4. Resources — must be a list, unique types
    resources = spec["resources"]
    if not isinstance(resources, list):
        errors.append("resources must be a list")
        return errors

    resource_types: list[str] = []
    for i, res in enumerate(resources):
        rtype = res.get("type")
        if not isinstance(rtype, str):
            errors.append(f"resources[{i}].type must be a string")
            continue
        if rtype in resource_types:
            errors.append(f"Duplicate resource type: '{rtype}'")
        resource_types.append(rtype)

        if not isinstance(res.get("count", 0), int) or res.get("count", 0) < 0:
            errors.append(f"resources[{i}].count must be a non-negative integer")
        if "properties" in res and not isinstance(res["properties"], dict):
            errors.append(f"resources[{i}].properties must be a dict")
        if "regenerate" in res and not isinstance(res["regenerate"], bool):
            errors.append(f"resources[{i}].regenerate must be a bool")

    # 5. Cross-reference: ConsumeEffect must reference existing resource types
    for i, action in enumerate(actions):
        effect = action.get("effect", {})
        if effect.get("type") == "ConsumeEffect":
            rt = effect.get("resource_type")
            if rt not in resource_types:
                errors.append(
                    f"actions[{i}] ConsumeEffect references resource_type '{rt}' which is not defined in resources"
                )

    return errors


# ---------------------------------------------------------------------------
# Spec → Environment conversion
# ---------------------------------------------------------------------------

from simlab.environment import (  # noqa: E402  — local import keeps this module's section ordering readable
    ActionRule,
    ConsumeEffect,
    Effect,
    Environment,
    MoveEffect,
    NoopEffect,
    ResourceRule,
)

_EFFECT_TYPES: dict[str, type] = {
    "MoveEffect": MoveEffect,
    "ConsumeEffect": ConsumeEffect,
    "NoopEffect": NoopEffect,
}


def _parse_effect(effect_dict: dict) -> Effect:
    """Convert a JSON effect dict to an Effect dataclass."""
    etype = effect_dict.get("type")
    cls = _EFFECT_TYPES.get(etype)
    if cls is None:
        raise ValueError(f"Unknown effect type '{etype}'. Valid: {set(_EFFECT_TYPES)}")

    # Only pass fields that the dataclass actually accepts
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in effect_dict.items() if k != "type" and k in valid_fields}
    return cls(**kwargs)


def _convert_ranges(properties: dict) -> dict:
    """Convert [min, max] lists to tuples for ResourceRule range values."""
    result = {}
    for k, v in properties.items():
        if isinstance(v, list):
            if len(v) != 2:
                raise ValueError(
                    f"Property range '{k}' must be [min, max], got {len(v)} elements"
                )
            result[k] = tuple(v)
        else:
            result[k] = v
    return result


def spec_to_environment(spec: dict, seed: int | None = None) -> Environment:
    """Build an Environment from a validated JSON spec.

    Validates first, then converts actions and resources into
    the dataclass types that Environment expects.
    """
    errors = validate_spec_dict(spec)
    if errors:
        raise ValueError(f"Invalid spec: {'; '.join(errors)}")

    actions = [
        ActionRule(name=a["name"], effect=_parse_effect(a["effect"]))
        for a in spec["actions"]
    ]
    resources = [
        ResourceRule(
            type=r["type"],
            properties=_convert_ranges(r.get("properties", {})),
            count=r.get("count", 0),
            regenerate=r.get("regenerate", True),
        )
        for r in spec["resources"]
    ]
    return Environment(
        width=spec["grid"]["width"],
        height=spec["grid"]["height"],
        actions=actions,
        resources=resources,
        seed=seed,
    )
