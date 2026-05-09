"""Defensive paradigm_slug injection for Variable nodes during extraction.

Post-P1-002, `paradigm_slug` is a required canonical Literal on
`_VariableProps`. The pre-validation backfill in `_build_result` exists
so the LLM-common pattern of emitting a Variable next to its parent
Paradigm without copying the slug down doesn't lose the Variable to
per-node validation.
"""

from decisionlab.knowledge.extraction import _build_result


def test_variable_inherits_paradigm_slug_from_batch():
    """Variable inherits paradigm_slug from a sibling Paradigm node when
    the LLM forgot to copy it down."""
    data = {
        "nodes": [
            {
                "label": "Paradigm",
                "natural_key": "slug",
                "properties": {"slug": "reinforcement-learning", "name": "RL"},
            },
            {
                "label": "Variable",
                "natural_key": "name",
                "properties": {"name": "reward", "type": "scalar"},
            },
        ],
    }
    result = _build_result(data, stage="researcher", run_id="r1")
    var = next(n for n in result.nodes if n.label == "Variable")
    assert var.properties["paradigm_slug"] == "reinforcement-learning"


def test_variable_keeps_explicit_paradigm_slug():
    """An explicit canonical paradigm_slug on the Variable wins over the
    batch's Paradigm slug — the inheritance is a backfill for missing
    values, not an override."""
    data = {
        "nodes": [
            {
                "label": "Paradigm",
                "natural_key": "slug",
                "properties": {"slug": "reinforcement-learning", "name": "RL"},
            },
            {
                "label": "Variable",
                "natural_key": "name",
                "properties": {"name": "x", "paradigm_slug": "prospect-theory"},
            },
        ],
    }
    result = _build_result(data, stage="researcher", run_id="r1")
    var = next(n for n in result.nodes if n.label == "Variable")
    assert var.properties["paradigm_slug"] == "prospect-theory"


def test_variable_without_paradigm_node_is_dropped():
    """Post-P1-002 contract: a Variable without paradigm_slug and no
    sibling Paradigm to inherit from fails per-node Pydantic validation
    and is dropped from the result. The pre-P1-002 "stays unscoped"
    behavior was the bug the canonical Literal was meant to close."""
    data = {
        "nodes": [
            {
                "label": "Variable",
                "natural_key": "name",
                "properties": {"name": "x"},
            },
        ],
    }
    result = _build_result(data, stage="researcher", run_id="r1")
    assert result.nodes == []
