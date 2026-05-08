"""Variable's unique key is now `id` (composite paradigm_slug:name),
not the bare `name`."""

from shared.knowledge_graph import KnowledgeGraph


def test_variable_unique_key_is_id():
    assert KnowledgeGraph.unique_key_for("Variable") == "id"


def test_variable_indexes_include_paradigm_slug():
    info = KnowledgeGraph.SCHEMA["Variable"]
    assert "paradigm_slug" in info["indexes"]
    assert "name" in info["indexes"]
