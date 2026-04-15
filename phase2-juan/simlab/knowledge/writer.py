"""TrackerMemoryWriter — persists Phase 2 simulation observations as memories.

This module is the public entry point of the `simlab.knowledge` package. It
defines the data classes that describe a simulation's context and the result of
a write operation, the `TrackerMemoryWriter` class that will orchestrate the
write pipeline (parse Tracker JSON -> embed -> upsert to Postgres + Qdrant),
and the `build_writer_from_settings` factory that wires the writer against real
infrastructure.

The full write logic is implemented incrementally across P1-002 (fact rules)
and P1-003 (orchestration). This scaffold (P1-001) only fixes the public
surface so downstream issues have stable signatures to depend on.

See docs/specs/sim-memory/phase-1-core-writer.md for the full specification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.embedding import EmbeddingService
    from shared.settings import Settings
    from shared.vector_store import VectorStore


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    """Identifies the Phase 1 model that governs an agent in a simulation.

    Used to attach paradigm/formulation metadata to every memory emitted from
    the simulation, enabling cross-phase retrieval by Pablo's Builder.
    """

    model_id: str
    class_name: str
    paradigm: str
    formulation: str
    phase1_run_id: str | None


@dataclass(frozen=True)
class SimulationContext:
    """Context of one simulation run required to enrich tracker-derived memories."""

    phase2_experiment_id: str
    environment: str
    steps: int
    seed: int | None
    agent_to_model: dict[str, ModelInfo]


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a `TrackerMemoryWriter.write` invocation.

    Counters report how many memories of each kind were persisted. When the
    writer short-circuits (invalid input, infra unavailable, etc.),
    `skipped_reason` is a short machine-readable string and counters are zero
    (or partial, if failure occurred mid-flight).
    """

    summaries_written: int
    trajectories_written: int
    episodes_written: int
    episodes_filtered: int
    duration_ms: int
    skipped_reason: str | None = None


# ---------------------------------------------------------------------------
# Writer (scaffold — real implementation lands in P1-003)
# ---------------------------------------------------------------------------


class TrackerMemoryWriter:
    """Writes simulation observations from the Tracker into the Knowledge Backbone.

    Real orchestration (parse, embed, upsert) is added in P1-003. This scaffold
    exists so P1-002 (fact rules) and the integration in Phase 2 can import a
    stable symbol while the logic is being built.
    """

    def __init__(
        self,
        *,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        db: DatabaseService,
    ) -> None:
        self._vectors = vector_store
        self._embeddings = embedding_service
        self._db = db

    async def write(
        self,
        tracker_output: str,
        context: SimulationContext,
    ) -> WriteResult:
        """Stub — returns a zeroed result with `skipped_reason='not_implemented'`.

        Implemented in P1-003.
        """
        return WriteResult(
            summaries_written=0,
            trajectories_written=0,
            episodes_written=0,
            episodes_filtered=0,
            duration_ms=0,
            skipped_reason="not_implemented",
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


async def build_writer_from_settings(settings: Settings) -> TrackerMemoryWriter | None:
    """Build a `TrackerMemoryWriter` wired to real infrastructure.

    Returns `None` (and logs a warning) if any of the following hold:
      - `VOYAGE_API_KEY` or `ZEROENTROPY_API_KEY` is empty.
      - Postgres or Qdrant cannot be reached.

    Callers in Phase 2 use `None` as the signal to silently skip knowledge
    writes — see the `ENABLE_KNOWLEDGE_WRITE` flag in the orchestrator.
    """
    if not settings.VOYAGE_API_KEY or not settings.ZEROENTROPY_API_KEY:
        logger.warning(
            "build_writer_from_settings: missing Voyage or ZeroEntropy API key — "
            "knowledge writes disabled"
        )
        return None

    # Imports are local so the module stays importable without the heavy
    # optional dependencies (qdrant, voyage) until the factory is actually used.
    from shared.database import DatabaseService
    from shared.embedding import EmbeddingService
    from shared.vector_store import VectorStore

    db = DatabaseService(settings)
    vector_store = VectorStore(settings)

    try:
        await db.connect()
    except Exception:
        logger.warning(
            "build_writer_from_settings: failed to connect to Postgres — "
            "knowledge writes disabled",
            exc_info=True,
        )
        return None

    try:
        await vector_store.connect()
        await vector_store.init_collections()
    except Exception:
        logger.warning(
            "build_writer_from_settings: failed to connect to Qdrant — "
            "knowledge writes disabled",
            exc_info=True,
        )
        await db.close()
        return None

    embedding_service = EmbeddingService(
        voyage_api_key=settings.VOYAGE_API_KEY,
        zeroentropy_api_key=settings.ZEROENTROPY_API_KEY,
    )

    return TrackerMemoryWriter(
        vector_store=vector_store,
        embedding_service=embedding_service,
        db=db,
    )
