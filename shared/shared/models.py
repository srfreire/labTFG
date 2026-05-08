"""SQLAlchemy 2.0 async ORM models for labtfg infrastructure."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("kind IN ('prod', 'eval')", name="runs_kind_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    problem_description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="created")
    kind: Mapped[str] = mapped_column(String(10), default="prod", server_default="prod")
    s3_report_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_prefix: Mapped[str] = mapped_column(String(500))
    artifact_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    memory_results: Mapped[dict | None] = mapped_column(
        "memory_results", JSONB, nullable=True
    )

    # relationships
    models: Mapped[list[Model]] = relationship(back_populates="run")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="run")


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("run_id", "paradigm", "formulation"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    class_name: Mapped[str] = mapped_column(String(255))
    paradigm: Mapped[str] = mapped_column(String(255))
    formulation: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )
    s3_model_key: Mapped[str] = mapped_column(String(500))
    s3_test_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # relationship
    run: Mapped[Run | None] = relationship(back_populates="models")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="created")
    spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    models_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s3_events_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_replay_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_tracker_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_analyst_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_pdf_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_tex_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_charts_prefix: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # relationships
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="experiment")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    s3_key: Mapped[str] = mapped_column(String(500), unique=True)
    artifact_type: Mapped[str] = mapped_column(String(50))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", name="artifacts_run_id_fkey", ondelete="CASCADE"),
        nullable=True,
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))

    # relationships
    run: Mapped[Run | None] = relationship(back_populates="artifacts")
    experiment: Mapped[Experiment | None] = relationship(back_populates="artifacts")


class NodeRunObservation(Base):
    """Per-run observation of a KG node MERGE.

    Replaces the unbounded ``n.run_ids`` array on Neo4j nodes (memory-refactor
    P0-004 / `docs/memory-system.md` §A10). Each MERGE in
    ``populate_kg._node_work`` inserts one row so per-run provenance stays
    queryable without bloating the graph payload.
    """

    __tablename__ = "node_run_observations"
    __table_args__ = (
        UniqueConstraint(
            "label", "key_value", "run_id", name="uq_node_run_observations_node_run"
        ),
        Index("ix_node_run_observations_run_id", "run_id"),
        Index("ix_node_run_observations_node", "label", "key_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(40))
    key_value: Mapped[str] = mapped_column(String(120))
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "runs.id",
            name="node_run_observations_run_id_fkey",
            ondelete="CASCADE",
        ),
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PipelineMemory(Base):
    """Phase 1 lifecycle memories: importance/confidence evolve via
    corroboration / contradiction / decay; bi-temporal via
    ``valid_from``/``valid_to`` plus a ``superseded_by`` chain.

    Always tied to a ``runs.id`` — Phase 1 writers always know which pipeline
    run produced the row (memory-refactor §A2 / phase-4 R3).
    """

    __tablename__ = "pipeline_memories"
    __table_args__ = (
        Index("ix_pipeline_memories_namespace", "namespace"),
        Index("ix_pipeline_memories_run_id", "run_id"),
        Index("ix_pipeline_memories_source_stage", "source_stage"),
        Index("ix_pipeline_memories_confidence", "confidence"),
        Index("ix_pipeline_memories_valid_to", "valid_to"),
        Index("ix_pipeline_memories_ns_confidence", "namespace", "confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content: Mapped[str] = mapped_column(Text)
    namespace: Mapped[str] = mapped_column(String(50))
    memory_type: Mapped[str] = mapped_column(String(50))
    source_stage: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "runs.id", name="pipeline_memories_run_id_fkey", ondelete="CASCADE"
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    corroborations: Mapped[int] = mapped_column(Integer, default=0)
    contradictions: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_memories.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # relationships
    run: Mapped[Run | None] = relationship()
    superseding_memory: Mapped[PipelineMemory | None] = relationship(
        remote_side=[id],
    )


class SimulationObservation(Base):
    """Phase 2 simulation observations: fixed confidence, no
    corroboration/supersession, typed cross-phase metadata fields.

    Phase 2's tracker emits one row per fact (summary, trajectory, episode);
    cross-phase joins land in real columns rather than JSONB blobs (§A2 /
    phase-4 R3).
    """

    __tablename__ = "simulation_observations"
    __table_args__ = (
        Index("ix_simulation_observations_phase2_experiment_id", "phase2_experiment_id"),
        Index("ix_simulation_observations_paradigm", "paradigm"),
        Index("ix_simulation_observations_formulation", "formulation"),
        Index("ix_simulation_observations_phase1_run_id", "phase1_run_id"),
        Index("ix_simulation_observations_memory_type", "memory_type"),
        Index("ix_simulation_observations_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content: Mapped[str] = mapped_column(Text)
    namespace: Mapped[str] = mapped_column(
        String(50), server_default="simulation", default="simulation"
    )
    memory_type: Mapped[str] = mapped_column(String(50))
    source_stage: Mapped[str] = mapped_column(
        String(100), server_default="tracker", default="tracker"
    )
    importance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(
        Float, server_default="0.80", default=0.80
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Cross-phase identifiers — typed columns instead of JSONB stuffing.
    # ``phase2_experiment_id`` is a String, not a UUID: the orchestrator can
    # pass an empty string when the experiment row hasn't been minted yet
    # (see simlab.orchestrator), and tests use opaque slugs like "exp-1".
    phase2_experiment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_class_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paradigm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    formulation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phase1_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "runs.id",
            name="simulation_observations_phase1_run_id_fkey",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    environment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    episode_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    step: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # relationships
    phase1_run: Mapped[Run | None] = relationship()
