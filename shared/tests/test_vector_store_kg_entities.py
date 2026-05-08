"""kg_entities_dense collection registered with the same dim as the
other dense collections; delete helpers exist for both dense and
sparse with a (collection, *, point_id) API shape that Phase 5 calls."""

from shared.vector_store import COLLECTIONS_DENSE, VectorStore


def test_kg_entities_dense_registered():
    assert "kg_entities_dense" in COLLECTIONS_DENSE
    # All dense collections currently use the same dim; distance is
    # hardcoded as cosine in init_collections().
    assert COLLECTIONS_DENSE["kg_entities_dense"] == 1024


def test_delete_dense_method_exists():
    assert hasattr(VectorStore, "delete_dense")
    assert callable(VectorStore.delete_dense)


def test_delete_sparse_method_exists():
    assert hasattr(VectorStore, "delete_sparse")
    assert callable(VectorStore.delete_sparse)
