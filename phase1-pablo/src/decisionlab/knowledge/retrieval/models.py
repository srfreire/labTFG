"""Data models shared across all retrieval channels."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalResult:
    """A single result from any retrieval channel (dense, sparse, KG, web)."""

    text: str
    score: float
    source: str
    metadata: dict = field(default_factory=dict)
