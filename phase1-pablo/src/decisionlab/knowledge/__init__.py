"""Knowledge backbone — extraction, cross-run memory and retrieval."""

from decisionlab.knowledge.extraction import extract
from decisionlab.knowledge.indexer import chunk_stage_output, index_stage_output
from decisionlab.knowledge.models import (
    Chunk,
    ExtractionResult,
    IndexResult,
    NodeSpec,
    RelationSpec,
    ResolutionResult,
)
from decisionlab.knowledge.resolver import resolve_and_store

__all__ = [
    "Chunk",
    "ExtractionResult",
    "IndexResult",
    "NodeSpec",
    "RelationSpec",
    "ResolutionResult",
    "chunk_stage_output",
    "extract",
    "index_stage_output",
    "resolve_and_store",
]
