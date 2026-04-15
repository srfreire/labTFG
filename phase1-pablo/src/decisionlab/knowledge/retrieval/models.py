"""Shared data models for retrieval channels."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RetrievalResult:
    """A single retrieval result from any channel (kg, dense, sparse, web)."""

    text: str
    score: float
    source: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CRAGResult:
    """Output of the Corrective RAG evaluation pipeline."""

    results: list[RetrievalResult]
    action: str  # "pass_through", "supplemented", "web_fallback"
    evaluations: list[dict] = field(default_factory=list)
    web_results_used: int = 0
