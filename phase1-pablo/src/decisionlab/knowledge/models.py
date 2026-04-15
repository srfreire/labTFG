"""Dataclasses for knowledge extraction and indexing results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeSpec:
    """A node to be written to the knowledge graph."""

    label: str
    """Neo4j label: Paradigm, Variable, Paper, etc."""

    properties: dict
    """All properties for the node."""

    natural_key: str
    """Property name used for dedup (e.g. 'slug', 'doi', 'id')."""


@dataclass
class RelationSpec:
    """A relation to be written to the knowledge graph."""

    from_label: str
    from_key_value: str
    """Natural key value of the source node."""

    to_label: str
    to_key_value: str
    """Natural key value of the target node."""

    rel_type: str
    """SUPPORTS, CONTRADICTS, etc."""

    properties: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Complete extraction output from one pipeline stage."""

    nodes: list[NodeSpec]
    relations: list[RelationSpec]
    facts: list[str]
    """Plain-text memory facts (atomic statements)."""

    stage: str
    """Which pipeline stage produced this."""

    run_id: str


@dataclass
class Chunk:
    """A chunk of text prepared for embedding and indexing."""

    text: str
    chunk_type: str
    """'artifact' or 'fact'."""

    source_section: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class KGWriteResult:
    """Summary of a knowledge graph population operation."""

    nodes_created: int
    nodes_merged: int
    relations_created: int
    relations_superseded: int
    errors: list[str] = field(default_factory=list)


@dataclass
class IndexResult:
    """Summary of an indexing operation."""

    artifacts_indexed: int
    facts_indexed: int
    total_chunks: int


@dataclass
class ResolutionResult:
    """Summary of a conflict resolution and memory persistence operation."""

    memories_created: int
    duplicates_skipped: int
    corroborations: int
    enrichments: int
    contradictions: int
    sonnet_calls: int
    importance_scores: dict = field(default_factory=dict)
