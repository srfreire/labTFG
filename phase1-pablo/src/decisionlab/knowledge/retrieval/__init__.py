"""Retrieval channels for the knowledge backbone."""

from decisionlab.knowledge.retrieval.crag import evaluate_results, web_fallback
from decisionlab.knowledge.retrieval.fusion import (
    fuse_and_rerank,
    rerank_results,
    rrf_fuse,
)
from decisionlab.knowledge.retrieval.kg_retrieval import kg_retrieve
from decisionlab.knowledge.retrieval.models import CRAGResult, RetrievalResult
from decisionlab.knowledge.retrieval.tool import (
    RETRIEVE_KNOWLEDGE_SCHEMA,
    create_retrieve_knowledge,
)

__all__ = [
    "RETRIEVE_KNOWLEDGE_SCHEMA",
    "CRAGResult",
    "RetrievalResult",
    "create_retrieve_knowledge",
    "evaluate_results",
    "fuse_and_rerank",
    "kg_retrieve",
    "rerank_results",
    "rrf_fuse",
    "web_fallback",
]
