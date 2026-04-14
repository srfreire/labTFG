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
