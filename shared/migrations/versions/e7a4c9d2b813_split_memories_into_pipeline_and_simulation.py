"""split memories into pipeline_memories and simulation_observations

Phase 4 R3 (memory-refactor) — the legacy ``memories`` table mixed Phase 1
lifecycle records (importance/confidence evolving via corroboration and
decay, supersession chains) with Phase 2 simulation observations (fixed
confidence, JSONB-stuffed cross-phase metadata, no supersession). This
revision creates two purpose-built tables, moves every existing row into
the correct one, and drops the old table.

Migration shape:
  - upgrade(): create both tables, copy rows, drop ``memories``.
  - downgrade(): re-create ``memories`` and copy rows back. The
    legacy ``valid_to``/``superseded_by``/JSONB shape is preserved on the
    way out so a rollback restores the same column set callers used pre-
    upgrade.

Data migration rules:
  - Rows with ``namespace = 'simulation'`` move into
    ``simulation_observations``. Their JSONB ``metadata`` is parsed into
    real columns (``phase2_experiment_id``, ``model_class_name``,
    ``paradigm``, ``formulation``, ``phase1_run_id``, ``environment``,
    ``steps``, ``seed``, ``agent_id``, ``episode_type``, ``step``);
    everything else stays in JSONB ``metadata``.
  - Every other row moves into ``pipeline_memories`` with a 1:1 column
    copy. Rows with NULL ``run_id`` (which the new schema forbids) are
    skipped — Phase 1 writers always set ``run_id``, so a NULL there is
    legacy debris from before the writer hardening landed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7a4c9d2b813"
down_revision: str | None = "a99972f4b668"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    _create_pipeline_memories()
    _create_simulation_observations()
    _migrate_rows()
    _drop_legacy_memories()


def downgrade() -> None:
    _recreate_legacy_memories()
    _migrate_rows_back()
    op.drop_index(
        "ix_simulation_observations_created_at",
        table_name="simulation_observations",
    )
    op.drop_index(
        "ix_simulation_observations_memory_type",
        table_name="simulation_observations",
    )
    op.drop_index(
        "ix_simulation_observations_phase1_run_id",
        table_name="simulation_observations",
    )
    op.drop_index(
        "ix_simulation_observations_formulation",
        table_name="simulation_observations",
    )
    op.drop_index(
        "ix_simulation_observations_paradigm",
        table_name="simulation_observations",
    )
    op.drop_index(
        "ix_simulation_observations_phase2_experiment_id",
        table_name="simulation_observations",
    )
    op.drop_table("simulation_observations")
    op.drop_index("ix_pipeline_memories_ns_confidence", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_valid_to", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_confidence", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_source_stage", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_run_id", table_name="pipeline_memories")
    op.drop_index("ix_pipeline_memories_namespace", table_name="pipeline_memories")
    op.drop_table("pipeline_memories")


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------


def _create_pipeline_memories() -> None:
    op.create_table(
        "pipeline_memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("namespace", sa.String(length=50), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("source_stage", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("corroborations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contradictions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "valid_from",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name="pipeline_memories_run_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["pipeline_memories.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pipeline_memories_namespace", "pipeline_memories", ["namespace"]
    )
    op.create_index("ix_pipeline_memories_run_id", "pipeline_memories", ["run_id"])
    op.create_index(
        "ix_pipeline_memories_source_stage",
        "pipeline_memories",
        ["source_stage"],
    )
    op.create_index(
        "ix_pipeline_memories_confidence",
        "pipeline_memories",
        ["confidence"],
    )
    op.create_index("ix_pipeline_memories_valid_to", "pipeline_memories", ["valid_to"])
    op.create_index(
        "ix_pipeline_memories_ns_confidence",
        "pipeline_memories",
        ["namespace", "confidence"],
    )


def _create_simulation_observations() -> None:
    op.create_table(
        "simulation_observations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "namespace",
            sa.String(length=50),
            nullable=False,
            server_default="simulation",
        ),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column(
            "source_stage",
            sa.String(length=100),
            nullable=False,
            server_default="tracker",
        ),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.80"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("phase2_experiment_id", sa.String(length=255), nullable=True),
        sa.Column("model_class_name", sa.String(length=255), nullable=True),
        sa.Column("paradigm", sa.String(length=255), nullable=True),
        sa.Column("formulation", sa.String(length=255), nullable=True),
        sa.Column("phase1_run_id", sa.UUID(), nullable=True),
        sa.Column("environment", sa.String(length=255), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("episode_type", sa.String(length=100), nullable=True),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["phase1_run_id"],
            ["runs.id"],
            name="simulation_observations_phase1_run_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_simulation_observations_phase2_experiment_id",
        "simulation_observations",
        ["phase2_experiment_id"],
    )
    op.create_index(
        "ix_simulation_observations_paradigm",
        "simulation_observations",
        ["paradigm"],
    )
    op.create_index(
        "ix_simulation_observations_formulation",
        "simulation_observations",
        ["formulation"],
    )
    op.create_index(
        "ix_simulation_observations_phase1_run_id",
        "simulation_observations",
        ["phase1_run_id"],
    )
    op.create_index(
        "ix_simulation_observations_memory_type",
        "simulation_observations",
        ["memory_type"],
    )
    op.create_index(
        "ix_simulation_observations_created_at",
        "simulation_observations",
        ["created_at"],
    )


def _drop_legacy_memories() -> None:
    op.drop_index("ix_memories_valid_to", table_name="memories")
    op.drop_index("ix_memories_source_stage", table_name="memories")
    op.drop_index("ix_memories_run_id", table_name="memories")
    op.drop_index("ix_memories_ns_confidence", table_name="memories")
    op.drop_index("ix_memories_namespace", table_name="memories")
    op.drop_index("ix_memories_confidence", table_name="memories")
    op.drop_table("memories")


def _recreate_legacy_memories() -> None:
    """Re-create the legacy ``memories`` table for downgrade.

    Mirrors ``bfb1033cc32f_add_memories_table`` so a rollback restores the
    same column set callers used pre-upgrade.
    """
    op.create_table(
        "memories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("namespace", sa.String(length=50), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("source_stage", sa.String(length=100), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("corroborations", sa.Integer(), nullable=False),
        sa.Column("contradictions", sa.Integer(), nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["memories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_confidence", "memories", ["confidence"])
    op.create_index("ix_memories_namespace", "memories", ["namespace"])
    op.create_index(
        "ix_memories_ns_confidence", "memories", ["namespace", "confidence"]
    )
    op.create_index("ix_memories_run_id", "memories", ["run_id"])
    op.create_index("ix_memories_source_stage", "memories", ["source_stage"])
    op.create_index("ix_memories_valid_to", "memories", ["valid_to"])


# ---------------------------------------------------------------------------
# Data migration
# ---------------------------------------------------------------------------


def _migrate_rows() -> None:
    """Move rows from ``memories`` into the two new tables.

    Phase 1 rows (namespace != 'simulation') are copied 1:1; rows with NULL
    ``run_id`` are skipped because the new ``pipeline_memories`` requires it.
    Phase 2 rows (namespace = 'simulation') are projected: JSONB ``metadata``
    fields are extracted into typed columns, with whatever doesn't fit kept
    in ``metadata``.
    """
    bind = op.get_bind()

    pipe_count = bind.execute(
        sa.text(
            """
            INSERT INTO pipeline_memories (
                id, content, namespace, memory_type, source_stage, run_id,
                created_at, updated_at, last_accessed_at, access_count,
                importance, confidence, corroborations, contradictions,
                valid_from, valid_to, superseded_by, metadata
            )
            SELECT
                id, content, namespace, memory_type, source_stage, run_id,
                created_at, updated_at, last_accessed_at, access_count,
                importance, confidence, corroborations, contradictions,
                valid_from, valid_to, superseded_by, metadata
            FROM memories
            WHERE namespace <> 'simulation'
              AND run_id IS NOT NULL
            """
        )
    ).rowcount

    skipped_pipe_no_run = bind.execute(
        sa.text(
            "SELECT count(*) FROM memories "
            "WHERE namespace <> 'simulation' AND run_id IS NULL"
        )
    ).scalar_one()

    sim_count = bind.execute(
        sa.text(
            """
            INSERT INTO simulation_observations (
                id, content, namespace, memory_type, source_stage,
                importance, confidence, created_at,
                phase2_experiment_id, model_class_name, paradigm,
                formulation, phase1_run_id, environment, steps, seed,
                agent_id, episode_type, step, metadata
            )
            SELECT
                id,
                content,
                namespace,
                memory_type,
                source_stage,
                importance,
                confidence,
                created_at,
                NULLIF(metadata->>'phase2_experiment_id', ''),
                NULLIF(metadata->>'model_class_name', ''),
                NULLIF(metadata->>'paradigm', ''),
                NULLIF(metadata->>'formulation', ''),
                CASE
                    WHEN NULLIF(metadata->>'phase1_run_id', '') IS NOT NULL
                    THEN (metadata->>'phase1_run_id')::uuid
                END,
                NULLIF(metadata->>'environment', ''),
                CASE
                    WHEN metadata->>'steps' ~ '^[0-9]+$'
                    THEN (metadata->>'steps')::int
                END,
                CASE
                    WHEN metadata->>'seed' ~ '^-?[0-9]+$'
                    THEN (metadata->>'seed')::int
                END,
                NULLIF(metadata->>'agent_id', ''),
                NULLIF(metadata->>'episode_type', ''),
                CASE
                    WHEN metadata->>'step' ~ '^[0-9]+$'
                    THEN (metadata->>'step')::int
                END,
                metadata - 'phase2_experiment_id' - 'model_class_name'
                         - 'paradigm' - 'formulation' - 'phase1_run_id'
                         - 'environment' - 'steps' - 'seed'
                         - 'agent_id' - 'episode_type' - 'step'
            FROM memories
            WHERE namespace = 'simulation'
            """
        )
    ).rowcount

    logger.info(
        "split_memories: copied %d pipeline + %d simulation rows; "
        "skipped %d pipeline rows with NULL run_id",
        pipe_count,
        sim_count,
        skipped_pipe_no_run,
    )


def _migrate_rows_back() -> None:
    """Copy rows back into ``memories`` for downgrade.

    The simulation rows reconstruct the JSONB ``metadata`` shape callers
    expected pre-upgrade so retrieval and tests keep working after a
    rollback.
    """
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            INSERT INTO memories (
                id, content, namespace, memory_type, source_stage, run_id,
                created_at, updated_at, last_accessed_at, access_count,
                importance, confidence, corroborations, contradictions,
                valid_from, valid_to, superseded_by, metadata
            )
            SELECT
                id, content, namespace, memory_type, source_stage, run_id,
                created_at, updated_at, last_accessed_at, access_count,
                importance, confidence, corroborations, contradictions,
                valid_from, valid_to, superseded_by, metadata
            FROM pipeline_memories
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO memories (
                id, content, namespace, memory_type, source_stage,
                created_at, updated_at, access_count,
                importance, confidence, corroborations, contradictions,
                valid_from, metadata
            )
            SELECT
                id, content, namespace, memory_type, source_stage,
                created_at, created_at, 0,
                importance, confidence, 0, 0,
                created_at,
                COALESCE(metadata, '{}'::jsonb)
                  || jsonb_strip_nulls(jsonb_build_object(
                      'phase2_experiment_id', phase2_experiment_id,
                      'model_class_name', model_class_name,
                      'paradigm', paradigm,
                      'formulation', formulation,
                      'phase1_run_id',
                          CASE WHEN phase1_run_id IS NOT NULL
                               THEN phase1_run_id::text END,
                      'environment', environment,
                      'steps', steps,
                      'seed', seed,
                      'agent_id', agent_id,
                      'episode_type', episode_type,
                      'step', step
                  ))
            FROM simulation_observations
            """
        )
    )
