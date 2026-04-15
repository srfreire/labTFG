"""Memory Agent — deterministic pipeline that runs after each pipeline stage.

Ties extraction, KG population, embedding/indexing, and conflict resolution
into a single ``run()`` call. NOT an agentic-loop agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Awaitable, Callable

from decisionlab.knowledge.extraction import extract
from decisionlab.knowledge.indexer import index_stage_output
from decisionlab.knowledge.kg_writer import populate_kg
from decisionlab.knowledge.models import (
    KGWriteResult,
    MemoryAgentResult,
    ResolutionResult,
)
from decisionlab.knowledge.resolver import resolve_and_store

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from shared.database import DatabaseService
    from shared.embedding import EmbeddingService
    from shared.knowledge_graph import KnowledgeGraph
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]


def _zero_kg() -> KGWriteResult:
    return KGWriteResult(
        nodes_created=0, nodes_merged=0, relations_created=0, relations_superseded=0
    )


def _zero_res() -> ResolutionResult:
    return ResolutionResult(
        memories_created=0,
        duplicates_skipped=0,
        corroborations=0,
        enrichments=0,
        contradictions=0,
        sonnet_calls=0,
    )


class MemoryAgent:
    """Deterministic pipeline: extract -> [KG + index] -> resolve."""

    def __init__(
        self,
        *,
        client: AsyncAnthropic,
        kg: KnowledgeGraph | None,
        vector_store: VectorStore | None,
        embedding_service: EmbeddingService | None,
        db: DatabaseService | None,
    ) -> None:
        self._client = client
        self._kg = kg
        self._vectors = vector_store
        self._embeddings = embedding_service
        self._db = db

    async def run(
        self,
        stage: str,
        stage_output: str,
        run_id: str,
        emit: EmitFn | None = None,
    ) -> MemoryAgentResult:
        """Run the full memory pipeline for one stage's output.

        Never raises — all errors are caught and logged, returning a zeroed
        result so the pipeline continues uninterrupted.
        """
        t0 = time.monotonic()

        async def _emit_status(status: str) -> None:
            if emit is not None:
                try:
                    await emit(
                        {
                            "type": "agent_status",
                            "agent": "memory_agent",
                            "status": status,
                        }
                    )
                except Exception:
                    logger.warning("Memory Agent: emit(%s) failed", status)

        try:
            await _emit_status("working")

            if not stage_output.strip():
                logger.warning(
                    "Memory Agent: empty stage output for stage=%s — skipping", stage
                )
                await _emit_status("done")
                return self._zero_result(t0)

            # Step 1: Extract entities, relations, facts
            try:
                extraction = await extract(stage, stage_output, run_id, self._client)
            except Exception:
                logger.exception("Memory Agent extraction failed for stage=%s", stage)
                await _emit_status("done")
                return self._zero_result(t0)

            # Step 2: Parallel KG population + embedding/indexing
            kg_result = await self._parallel_write(
                extraction, stage, stage_output, run_id
            )

            # Step 3: Conflict resolution + memory persistence
            res_result = await self._resolve(extraction)

            await _emit_status("done")

            result = MemoryAgentResult(
                nodes_created=kg_result.nodes_created,
                nodes_merged=kg_result.nodes_merged,
                relations_created=kg_result.relations_created,
                facts_stored=res_result.memories_created,
                duplicates_skipped=res_result.duplicates_skipped,
                conflicts_resolved=res_result.contradictions,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            logger.info(
                "Memory Agent [%s]: %d nodes (+%d merged), %d relations, "
                "%d facts stored, %d dups skipped, %d conflicts — %dms",
                stage,
                result.nodes_created,
                result.nodes_merged,
                result.relations_created,
                result.facts_stored,
                result.duplicates_skipped,
                result.conflicts_resolved,
                result.duration_ms,
            )
            return result

        except Exception:
            logger.exception("Memory Agent failed for stage=%s", stage)
            await _emit_status("done")
            return self._zero_result(t0)

    # -- internal helpers ----------------------------------------------------

    async def _parallel_write(
        self,
        extraction,
        stage: str,
        stage_output: str,
        run_id: str,
    ) -> KGWriteResult:
        """Run KG population and embedding/indexing in parallel.

        Returns the KG result (zeroed if KG is unavailable or fails).
        Indexing errors are logged but do not affect the return value.
        """
        do_kg = self._kg is not None
        do_idx = self._vectors is not None and self._embeddings is not None

        if not do_kg and not do_idx:
            return _zero_kg()

        # Build named tasks so results can be identified without index tracking
        coros: dict[str, asyncio.Task] = {}
        if do_kg:
            coros["kg"] = asyncio.create_task(populate_kg(extraction, self._kg))
        if do_idx:
            coros["idx"] = asyncio.create_task(
                index_stage_output(
                    stage,
                    stage_output,
                    extraction,
                    self._embeddings,
                    self._vectors,
                    run_id,
                )
            )

        results = await asyncio.gather(*coros.values(), return_exceptions=True)
        named = dict(zip(coros, results))

        kg_result = _zero_kg()
        if "kg" in named:
            r = named["kg"]
            if isinstance(r, BaseException):
                logger.error("KG population failed: %s", r, exc_info=r)
            else:
                kg_result = r

        if "idx" in named:
            r = named["idx"]
            if isinstance(r, BaseException):
                logger.error("Indexing failed: %s", r, exc_info=r)

        return kg_result

    async def _resolve(self, extraction) -> ResolutionResult:
        """Run conflict resolution if all required infra is available."""
        if self._vectors is None or self._embeddings is None or self._db is None:
            return _zero_res()

        try:
            async with self._db.get_session() as session:
                result = await resolve_and_store(
                    extraction, self._embeddings, self._vectors, session, self._client
                )
                await session.commit()
            return result
        except Exception:
            logger.exception("Memory Agent resolution failed")
            return _zero_res()

    @staticmethod
    def _zero_result(t0: float) -> MemoryAgentResult:
        return MemoryAgentResult(
            nodes_created=0,
            nodes_merged=0,
            relations_created=0,
            facts_stored=0,
            duplicates_skipped=0,
            conflicts_resolved=0,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
