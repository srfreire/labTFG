"""Knowledge extraction module for the DecisionLab pipeline."""

from decisionlab.knowledge.extraction import extract
from decisionlab.knowledge.models import (
    ExtractionResult,
    NodeSpec,
    RelationSpec,
)

__all__ = [
    "ExtractionResult",
    "NodeSpec",
    "RelationSpec",
    "extract",
]
