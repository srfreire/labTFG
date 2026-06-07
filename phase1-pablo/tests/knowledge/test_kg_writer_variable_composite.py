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


def test_variable_without_paradigm_uses_orphan_namespace():
    """Orphan variable — no paradigm context — gets scoped under `orphan:`.

    The orphan namespace is load-bearing: it prevents an unscoped variable
    from silently merging with a paradigm-scoped one of the same name.
    """
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {"name": "reward"},
        },
    )()
    out = _resolve_natural_key(spec)
    assert out == ("id", "orphan:reward")


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


def test_variable_with_formulation_still_uses_paradigm_scope():
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {
                "name": "reward",
                "formulation_id": "q-learning",
                "paradigm_slug": "reinforcement-learning",
            },
        },
    )()
    out = _resolve_natural_key(spec)
    assert out == ("id", "reinforcement-learning:reward")
    assert spec.properties["formulation_id"] == "reinforcement-learning:q-learning"


def test_variable_missing_name_returns_none():
    spec = type("_Spec", (), {"label": "Variable", "properties": {}})()
    assert _resolve_natural_key(spec) is None


def test_variable_non_string_name_returns_none():
    spec = type(
        "_Spec",
        (),
        {"label": "Variable", "properties": {"name": 123}},
    )()
    assert _resolve_natural_key(spec) is None


def test_variable_name_empty_after_slugify_returns_none():
    """A name that slugifies to "" (e.g. only punctuation) is unrecoverable."""
    spec = type(
        "_Spec",
        (),
        {
            "label": "Variable",
            "properties": {"name": "!!!", "paradigm_slug": "reinforcement-learning"},
        },
    )()
    assert _resolve_natural_key(spec) is None
