"""TrackerMemoryWriter — persists Phase 2 simulation observations as memories.

Orchestrates the full write pipeline: parse Tracker JSON → build facts →
embed (Voyage, single batch) → insert into Postgres
memories table + upsert to Qdrant memories_dense/memories_sparse. All
operations share the same UUID per fact to keep the three stores joinable.

See docs/specs/sim-memory/phase-1-core-writer.md for the full specification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from asyncio import CancelledError
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from shared.memories import create_memory

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.embedding import EmbeddingService
    from shared.settings import Settings
    from shared.vector_store import VectorStore
    from simlab.knowledge.facts import FactSpec


logger = logging.getLogger(__name__)

_NAMESPACE = "simulation"
_SOURCE_STAGE = "tracker"
_CONFIDENCE = 0.80
_COLLECTION_DENSE = "memories_dense"
_COLLECTION_SPARSE = "memories_sparse"


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
# Private helpers
# ---------------------------------------------------------------------------


def _zero_result(
    t0: float,
    *,
    episodes_filtered: int = 0,
    skipped_reason: str | None = None,
) -> WriteResult:
    return WriteResult(
        summaries_written=0,
        trajectories_written=0,
        episodes_written=0,
        episodes_filtered=episodes_filtered,
        duration_ms=int((time.monotonic() - t0) * 1000),
        skipped_reason=skipped_reason,
    )


class _Counters:
    __slots__ = ("episodes", "summaries", "trajectories")

    def __init__(self) -> None:
        self.summaries = 0
        self.trajectories = 0
        self.episodes = 0

    def count(self, fact: FactSpec) -> None:
        if fact.memory_type == "episodic":
            self.episodes += 1
        elif "agent_id" in fact.metadata:
            self.trajectories += 1
        else:
            self.summaries += 1

    @property
    def total(self) -> int:
        return self.summaries + self.trajectories + self.episodes


def _build_payload(memory_id: uuid.UUID, fact: FactSpec) -> dict[str, Any]:
    return {
        "memory_id": str(memory_id),
        "namespace": _NAMESPACE,
        "source_stage": _SOURCE_STAGE,
        **fact.metadata,
    }


async def _safe_upsert(
    kind: str,
    coro,
    memory_id: uuid.UUID,
) -> None:
    """Await a Qdrant upsert; log and swallow any failure so the batch keeps going.

    The Postgres row is already committed (or will be), so a failed vector
    upsert is recoverable via consolidation.
    """
    try:
        await coro
    except CancelledError:
        raise
    except Exception:
        logger.warning(
            "TrackerMemoryWriter: %s upsert failed for memory %s — "
            "Postgres row kept, retry via consolidation",
            kind,
            memory_id,
            exc_info=True,
        )


async def _upsert_vectors(
    vector_store: VectorStore,
    memory_id: uuid.UUID,
    dense: list[float],
    text: str,
    payload: dict[str, Any],
) -> None:
    """Upsert dense + sparse for one memory in parallel; swallow individual failures."""
    mem_id_str = str(memory_id)
    coros = [
        _safe_upsert(
            "dense",
            vector_store.upsert_dense(_COLLECTION_DENSE, mem_id_str, dense, payload),
            memory_id,
        ),
        _safe_upsert(
            "sparse",
            vector_store.upsert_sparse(_COLLECTION_SPARSE, mem_id_str, text, payload),
            memory_id,
        ),
    ]
    await asyncio.gather(*coros)


class TrackerMemoryWriter:
    """Writes simulation observations from the Tracker into the Knowledge Backbone.

    One UUID is minted per fact and reused across the Postgres row, the dense
    Qdrant point, and the sparse Qdrant point so downstream retrieval can join
    the three stores. Per-fact failures in Qdrant are logged and skipped; the
    Postgres row is kept and recoverable by the consolidation job.
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
        """Persist facts derived from the Tracker output to Postgres + Qdrant.

        Never raises except for CancelledError — any other failure is captured,
        logged, and reflected as a `skipped_reason` in the returned WriteResult.
        """
        t0 = time.monotonic()

        try:
            return await self._write(tracker_output, context, t0)
        except CancelledError:
            raise
        except BaseException as exc:
            logger.exception("TrackerMemoryWriter.write failed unexpectedly")
            return _zero_result(
                t0,
                skipped_reason=f"error: {type(exc).__name__}: {exc}",
            )

    async def _write(
        self,
        tracker_output: str,
        context: SimulationContext,
        t0: float,
    ) -> WriteResult:
        # Local imports so the module stays cheap to import and the
        # Phase-1 tokenizer dependency only matters when we actually write.
        from simlab.knowledge.facts import build_all_facts

        try:
            tracker = json.loads(tracker_output)
        except (json.JSONDecodeError, TypeError):
            return _zero_result(t0, skipped_reason="invalid_json")

        if not isinstance(tracker, dict):
            return _zero_result(t0, skipped_reason="invalid_json")

        facts, episodes_filtered = build_all_facts(tracker, context)
        if not facts:
            return _zero_result(
                t0,
                episodes_filtered=episodes_filtered,
                skipped_reason="no_relevant_content",
            )

        texts = [f.text for f in facts]
        dense_vectors = await self._embeddings.embed_texts(texts)

        counters = _Counters()

        async with self._db.get_session() as session:
            for fact, dense in zip(facts, dense_vectors, strict=True):
                memory_id = uuid.uuid4()
                payload = _build_payload(memory_id, fact)

                await create_memory(
                    session,
                    id=memory_id,
                    content=fact.text,
                    namespace=_NAMESPACE,
                    memory_type=fact.memory_type,
                    source_stage=_SOURCE_STAGE,
                    run_id=None,
                    importance=fact.importance,
                    confidence=_CONFIDENCE,
                    metadata_=dict(fact.metadata),
                )

                await _upsert_vectors(
                    self._vectors, memory_id, dense, fact.text, payload
                )

                counters.count(fact)

            await session.commit()

        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "TrackerMemoryWriter: wrote %d memories to namespace=%s — "
            "%d summaries, %d trajectories, %d episodes, %d filtered, %dms",
            counters.total,
            _NAMESPACE,
            counters.summaries,
            counters.trajectories,
            counters.episodes,
            episodes_filtered,
            duration_ms,
        )

        return WriteResult(
            summaries_written=counters.summaries,
            trajectories_written=counters.trajectories,
            episodes_written=counters.episodes,
            episodes_filtered=episodes_filtered,
            duration_ms=duration_ms,
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
