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
class IndexResult:
    """Summary of an indexing operation."""

    artifacts_indexed: int
    facts_indexed: int
    total_chunks: int
