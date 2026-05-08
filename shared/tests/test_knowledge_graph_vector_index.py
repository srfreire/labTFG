"""P4-002: native Neo4j vector index for slug-like nodes replaces the
dropped Qdrant ``kg_entities_dense`` collection.

Unit tests cover the public surface (``vector_index_name`` helper, the
configured label set, and the dimension constant). The Cypher
``CREATE VECTOR INDEX`` statement issued by ``init_schema`` is exercised
end-to-end by the integration suite.
"""

import pytest

from shared.knowledge_graph import (
    _VECTOR_INDEX_DIMENSIONS,
    _VECTOR_INDEX_LABELS,
    vector_index_name,
)


def test_vector_index_labels_cover_slug_like_set():
    """The five slug-like labels that retrieval entity-links against."""
    assert set(_VECTOR_INDEX_LABELS) == {
        "Paradigm",
        "Variable",
        "Postulate",
        "Formulation",
        "Model",
    }


def test_vector_index_dimensions_match_voyage_output():
    """1024d cosine — same as the dropped Qdrant collection."""
    assert _VECTOR_INDEX_DIMENSIONS == 1024


def test_vector_index_name_lowercases_label():
    assert vector_index_name("Paradigm") == "paradigm_embedding_idx"
    assert vector_index_name("Variable") == "variable_embedding_idx"


def test_vector_index_name_rejects_unsupported_label():
    with pytest.raises(ValueError, match="No vector index"):
        vector_index_name("Paper")
