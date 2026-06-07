"""Memory Agent — deterministic pipeline that runs after each pipeline stage.

Ties extraction, KG population, embedding/indexing, and conflict resolution
into a single ``run()`` call. NOT an agentic-loop agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from decisionlab.knowledge.canonicalize import canonicalize_extraction
from decisionlab.knowledge.extraction import extract
from decisionlab.knowledge.graph_review import review_written_graph
from decisionlab.knowledge.ids import (
    align_to_approved_formulations,
    materialize_structural_relations,
    normalize_extraction_ids,
    prune_relationless_leaf_nodes,
    prune_to_approved_context,
    prune_unresolvable_relations,
)
from decisionlab.knowledge.kg_health import audit_kg_health
from decisionlab.knowledge.kg_writer import populate_kg
from decisionlab.knowledge.models import (
    KGHealthResult,
    KGReviewResult,
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
_EXTRACTION_TIMEOUT_SECONDS = float(
    os.getenv("DECISIONLAB_MEMORY_EXTRACTION_TIMEOUT_SECONDS", "900")
)


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
        approved_paradigms: list[str] | tuple[str, ...] | set[str] | None = None,
        approved_specs: dict[str, list[str] | tuple[str, ...] | set[str]] | None = None,
    ) -> MemoryAgentResult:
        """Run the full memory pipeline for one stage's output.

        Never raises — all errors are caught and logged. On failure the
        returned result has ``failed=True`` and the emitted ``agent_status``
        is ``failed`` (with the error message) so the UI can surface it.
        """
        t0 = time.monotonic()

        async def _emit_status(status: str, error: str | None = None) -> None:
            if emit is None:
                return
            payload = {
                "type": "agent_status",
                "agent": "memory_agent",
                "status": status,
            }
            if error is not None:
                payload["error"] = error
            try:
                await emit(payload)
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
                extraction = await asyncio.wait_for(
                    extract(stage, stage_output, run_id, self._client),
                    timeout=_EXTRACTION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.exception(
                    "Memory Agent extraction timed out for stage=%s", stage
                )
                await _emit_status("failed", error="extraction: timed out")
                return self._failed_result(t0, "extraction: timed out")
            except Exception as exc:
                logger.exception("Memory Agent extraction failed for stage=%s", stage)
                await _emit_status("failed", error=f"extraction: {exc}")
                return self._failed_result(t0, f"extraction: {exc}")

            # Step 1b: Resolve __NEW__ paradigm slugs against the existing KG
            # before writes. Errors here are non-fatal — fall through with the
            # raw extraction (per-label validation downstream drops orphans).
            if self._kg is not None and self._embeddings is not None:
                try:
                    extraction = await canonicalize_extraction(
                        extraction,
                        kg=self._kg,
                        embeddings=self._embeddings,
                        client=self._client,
                    )
                except Exception:
                    logger.exception(
                        "Memory Agent: canonicalize_extraction raised — "
                        "proceeding with raw extraction"
                    )

            # Step 1c: deterministic identity normalization and context pruning.
            align_to_approved_formulations(
                extraction,
                approved_specs=approved_specs,
            )
            normalize_extraction_ids(extraction)
            prune_to_approved_context(
                extraction,
                approved_paradigms=approved_paradigms,
                approved_specs=approved_specs,
            )

            # Step 2: deterministic graph structure. This is not LLM review:
            # it materializes ownership edges implied by scoped IDs/properties
            # before Neo4j sees the batch.
            normalize_extraction_ids(extraction)
            before_prune = len(extraction.nodes)
            prune_relationless_leaf_nodes(extraction)
            pruned = before_prune - len(extraction.nodes)
            if pruned:
                logger.info(
                    "Memory Agent [%s]: pruned %d relationless literature node(s)",
                    stage,
                    pruned,
                )
            before_relations = len(extraction.relations)
            prune_unresolvable_relations(extraction)
            pruned_relations = before_relations - len(extraction.relations)
            if pruned_relations:
                logger.info(
                    "Memory Agent [%s]: pruned %d unresolvable relation(s)",
                    stage,
                    pruned_relations,
                )
            materialize_structural_relations(extraction)
            prune_unresolvable_relations(extraction)

            # Step 3: KG population. Fact vectors are indexed by the resolver
            # after PG memory rows exist, so Qdrant and Postgres share ids.
            kg_result = await self._write_kg(extraction)
            kg_review = await self._review_graph(
                stage=stage,
                run_id=run_id,
                stage_output=stage_output,
                approved_paradigms=approved_paradigms,
                approved_specs=approved_specs,
            )
            kg_health = await self._audit_kg_health(extraction)

            # Step 4: Conflict resolution + memory persistence
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
                kg_errors=kg_result.errors,
                kg_health=kg_health,
                kg_review=kg_review,
            )
            logger.info(
                "Memory Agent [%s]: %d nodes (+%d merged), %d relations, "
                "%d facts stored, %d dups skipped, %d conflicts, %d KG errors, "
                "%d graph review corrections, %d health repairs — %dms",
                stage,
                result.nodes_created,
                result.nodes_merged,
                result.relations_created,
                result.facts_stored,
                result.duplicates_skipped,
                result.conflicts_resolved,
                len(result.kg_errors),
                kg_review.corrections_applied if kg_review else 0,
                kg_health.inferred_relations_created if kg_health else 0,
                result.duration_ms,
            )
            return result

        except Exception as exc:
            logger.exception("Memory Agent failed for stage=%s", stage)
            await _emit_status("failed", error=str(exc))
            return self._failed_result(t0, str(exc))

    # -- internal helpers ----------------------------------------------------

    async def _write_kg(
        self,
        extraction,
    ) -> KGWriteResult:
        """Run KG population, zeroing the result if KG is unavailable/fails."""
        do_kg = self._kg is not None

        if not do_kg:
            return _zero_kg()

        try:
            return await populate_kg(
                extraction,
                self._kg,
                db=self._db,
                embeddings=self._embeddings,
                vectors=self._vectors,
            )
        except Exception as exc:
            logger.error("KG population failed: %s", exc, exc_info=exc)
            return _zero_kg()

    async def _review_graph(
        self,
        *,
        stage: str,
        run_id: str,
        stage_output: str,
        approved_paradigms,
        approved_specs,
    ) -> KGReviewResult | None:
        """Run post-write graph review against the persisted graph."""
        if self._kg is None or self._db is None:
            return None
        try:
            return await review_written_graph(
                stage=stage,
                run_id=run_id,
                stage_output=stage_output,
                kg=self._kg,
                db=self._db,
                client=self._client,
                approved_paradigms=approved_paradigms,
                approved_specs=approved_specs,
            )
        except Exception:
            logger.exception("Memory Agent graph review failed")
            return KGReviewResult(
                corrections_applied=0,
                failed=True,
                error="graph review failed",
            )

    async def _audit_kg_health(self, extraction) -> KGHealthResult | None:
        """Run post-write KG readability audit without repairs."""
        if self._kg is None:
            return None
        try:
            return await audit_kg_health(extraction, self._kg)
        except Exception:
            logger.exception("Memory Agent KG health audit failed")
            return None

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

    @staticmethod
    def _failed_result(t0: float, error: str) -> MemoryAgentResult:
        return MemoryAgentResult(
            nodes_created=0,
            nodes_merged=0,
            relations_created=0,
            facts_stored=0,
            duplicates_skipped=0,
            conflicts_resolved=0,
            duration_ms=int((time.monotonic() - t0) * 1000),
            failed=True,
            error=error,
        )
