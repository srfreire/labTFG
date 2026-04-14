"""Retrieval channels for the knowledge backbone."""

from decisionlab.knowledge.retrieval.fusion import fuse_and_rerank, rerank_results, rrf_fuse
from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve
from decisionlab.knowledge.retrieval.models import RetrievalResult

__all__ = [
    "RetrievalResult",
    "fuse_and_rerank",
    "kg_retrieve",
    "rerank_results",
    "rrf_fuse",
]
