"""SQLAlchemy 2.0 async ORM models for labtfg infrastructure."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    problem_description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="created")
    s3_report_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_prefix: Mapped[str] = mapped_column(String(500))

    # relationships
    models: Mapped[list[Model]] = relationship(back_populates="run")
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="run")


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("run_id", "paradigm", "formulation"),
    )

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
    s3_test_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # relationship
    run: Mapped[Run | None] = relationship(back_populates="models")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="created")
    spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    models_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s3_events_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_replay_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_tracker_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_analyst_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_pdf_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_tex_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    s3_charts_prefix: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # relationships
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="experiment"
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    s3_key: Mapped[str] = mapped_column(String(500), unique=True)
    artifact_type: Mapped[str] = mapped_column(String(50))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(100))

    # relationships
    run: Mapped[Run | None] = relationship(back_populates="artifacts")
    experiment: Mapped[Experiment | None] = relationship(
        back_populates="artifacts"
    )


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_namespace", "namespace"),
        Index("ix_memories_run_id", "run_id"),
        Index("ix_memories_source_stage", "source_stage"),
        Index("ix_memories_confidence", "confidence"),
        Index("ix_memories_valid_to", "valid_to"),
        Index("ix_memories_ns_confidence", "namespace", "confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content: Mapped[str] = mapped_column(Text)
    namespace: Mapped[str] = mapped_column(String(50))
    memory_type: Mapped[str] = mapped_column(String(50))
    source_stage: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    corroborations: Mapped[int] = mapped_column(Integer, default=0)
    contradictions: Mapped[int] = mapped_column(Integer, default=0)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id"), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # relationships
    run: Mapped[Run | None] = relationship()
    superseding_memory: Mapped[Memory | None] = relationship(
        remote_side=[id],
    )
