"""Defensive paradigm_slug injection for Variable nodes during extraction."""

from decisionlab.knowledge.extraction import _build_result


def test_variable_inherits_paradigm_slug_from_batch():
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
    """An explicit paradigm_slug on the Variable wins over batch fallback."""
    data = {
        "nodes": [
            {
                "label": "Paradigm",
                "natural_key": "slug",
                "properties": {"slug": "from-paradigm-node", "name": "P"},
            },
            {
                "label": "Variable",
                "natural_key": "name",
                "properties": {"name": "x", "paradigm_slug": "explicit-slug"},
            },
        ],
    }
    result = _build_result(data, stage="researcher", run_id="r1")
    var = next(n for n in result.nodes if n.label == "Variable")
    assert var.properties["paradigm_slug"] == "explicit-slug"


def test_variable_without_paradigm_node_stays_unscoped():
    """No Paradigm in batch → Variable stays without paradigm_slug (orphan
    branch will tag it later in kg_writer)."""
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
    var = result.nodes[0]
    assert "paradigm_slug" not in var.properties
