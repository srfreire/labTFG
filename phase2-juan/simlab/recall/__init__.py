"""Knowledge Backbone readers for Phase 2 agents.

See docs/specs/sim-recall/ for the full design.
"""

from simlab.recall.agent_tools import build_recall_extras
from simlab.recall.retrieve import (
    RETRIEVE_CONTEXT_TOOL,
    build_retriever_from_settings,
    retrieve_context,
)

__all__ = [
    "RETRIEVE_CONTEXT_TOOL",
    "build_recall_extras",
    "build_retriever_from_settings",
    "retrieve_context",
]
