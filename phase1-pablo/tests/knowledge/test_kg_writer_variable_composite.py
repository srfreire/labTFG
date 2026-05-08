"""Variable nodes get id = {paradigm_slug}:{slugify(name)} when
paradigm_slug is in their properties."""

from decisionlab.knowledge.kg_writer import _resolve_natural_key


def test_variable_with_paradigm_gets_composite_id():
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {"name": "reward", "paradigm_slug": "reinforcement-learning"},
        },
    )()
    out = _resolve_natural_key(spec)
    assert out == ("id", "reinforcement-learning:reward")


def test_variable_without_paradigm_falls_back_to_name():
    """Orphan variable — no paradigm context — gets unscoped id."""
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {"name": "reward"},
        },
    )()
    out = _resolve_natural_key(spec)
    # Orphan tag — accept either bare name or "orphan:reward"; pick whichever
    # the implementation chooses, just don't silently merge with the scoped one.
    assert out is not None
    label, value = out
    assert label == "id"
    assert value != "reinforcement-learning:reward"


def test_variable_id_normalises_name():
    """Inner spaces / mixed case in name → slugified before composite."""
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {
                "name": "Action Value",
                "paradigm_slug": "reinforcement-learning",
            },
        },
    )()
    out = _resolve_natural_key(spec)
    assert out == ("id", "reinforcement-learning:action-value")
