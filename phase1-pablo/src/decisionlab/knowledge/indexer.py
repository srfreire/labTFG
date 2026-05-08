"""Embedding and Qdrant indexing pipeline for artifacts and facts (P2-003).

Takes pipeline stage output text and extracted facts, chunks them by
stage-specific strategy, embeds via Voyage AI, and upserts to Qdrant
dense + sparse collections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from decisionlab.knowledge.models import Chunk, ExtractionResult, IndexResult

if TYPE_CHECKING:
    from shared.embedding import EmbeddingService
    from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)

_STAGE_NAMESPACE: dict[str, str] = {
    "researcher": "paradigm",
    "formalizer": "formulation",
    "reasoner": "formulation",
    "builder": "model",
}

_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_FORMULATION_RE = re.compile(r"^###\s+(Formulation\s+\d+:.+)$", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)

_LARGE_JSON_THRESHOLD = 4000


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_stage_output(stage: str, text: str) -> list[Chunk]:
    """Split stage output into chunks using a stage-specific strategy."""
    if not text.strip():
        return []

    if stage == "researcher":
        return _chunk_researcher(text)
    if stage == "formalizer":
        return _chunk_formalizer(text)
    if stage == "reasoner":
        return _chunk_reasoner(text)
    if stage == "builder":
        return _chunk_builder(text)
    raise ValueError(f"Unknown stage: {stage!r}")


def _iter_header_body_pairs(splits: list[str]) -> list[tuple[str, str]]:
    """Extract (header, body) pairs from a regex split result.

    ``re.split`` with a capturing group returns [preamble, h1, b1, h2, b2, ...].
    Pairs whose body is blank are skipped.
    """
    pairs: list[tuple[str, str]] = []
    i = 1
    while i < len(splits) - 1:
        header = splits[i].strip()
        body = splits[i + 1].strip()
        if body:
            pairs.append((header, body))
        i += 2
    return pairs


def _chunk_researcher(text: str) -> list[Chunk]:
    """Split by ## section headers. Prepend paradigm name to each chunk."""
    paradigm = ""
    first_h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if first_h1:
        paradigm = first_h1.group(1).strip()

    chunks: list[Chunk] = []
    for header, body in _iter_header_body_pairs(_SECTION_RE.split(text)):
        prefix = f"{paradigm}\n\n" if paradigm else ""
        chunk_text = f"{prefix}## {header}\n{body}"
        chunks.append(
            Chunk(text=chunk_text, chunk_type="artifact", source_section=header)
        )
    return chunks


def _chunk_formalizer(text: str) -> list[Chunk]:
    """Split by ### Formulation N: headers."""
    return [
        Chunk(
            text=f"### {header}\n{body}", chunk_type="artifact", source_section=header
        )
        for header, body in _iter_header_body_pairs(_FORMULATION_RE.split(text))
    ]


def _chunk_reasoner(text: str) -> list[Chunk]:
    """Full JSON as one chunk if <=4K chars, otherwise split by top-level keys."""
    if len(text) <= _LARGE_JSON_THRESHOLD:
        return [Chunk(text=text, chunk_type="artifact")]

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return [Chunk(text=text, chunk_type="artifact")]

    if not isinstance(data, dict):
        return [Chunk(text=text, chunk_type="artifact")]

    chunks: list[Chunk] = []
    for key, value in data.items():
        chunk_text = json.dumps({key: value})
        chunks.append(Chunk(text=chunk_text, chunk_type="artifact", source_section=key))

    return chunks


def _chunk_builder(text: str) -> list[Chunk]:
    """Model .py is one chunk, test .py is another. Detect code blocks or treat as single file."""
    blocks = _CODE_BLOCK_RE.findall(text)
    if len(blocks) >= 2:
        return [
            Chunk(
                text=blocks[0].strip(), chunk_type="artifact", source_section="model"
            ),
            Chunk(text=blocks[1].strip(), chunk_type="artifact", source_section="test"),
        ]
    # Single file or no code blocks — entire text is one chunk
    return [Chunk(text=text.strip(), chunk_type="artifact")]


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def _make_point_id(run_id: str, stage: str, chunk_index: int) -> str:
    """Deterministic UUID from run_id:stage:chunk_index."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{run_id}:{stage}:{chunk_index}"))


async def index_stage_output(
    stage: str,
    output_text: str,
    extraction: ExtractionResult,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    run_id: str,
) -> IndexResult:
    """Chunk, embed, and upsert stage output + extracted facts to Qdrant."""
    artifact_chunks = chunk_stage_output(stage, output_text)
    fact_chunks = [Chunk(text=f, chunk_type="fact") for f in extraction.facts]

    all_chunks = artifact_chunks + fact_chunks
    if not all_chunks:
        return IndexResult(artifacts_indexed=0, facts_indexed=0, total_chunks=0)

    # Embed all chunks in one batch
    texts = [c.text for c in all_chunks]
    vectors = await embedding_service.embed_texts(texts)
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"embed_texts returned {len(vectors)} vectors for {len(texts)} texts "
            f"(stage={stage!r}, run_id={run_id!r})"
        )

    namespace = _STAGE_NAMESPACE.get(stage, "meta")
    now = datetime.now(UTC).isoformat()

    _COLLECTION_PREFIX = {"artifact": "artifacts", "fact": "memories"}

    upsert_tasks = []
    for i, chunk in enumerate(all_chunks):
        point_id = _make_point_id(run_id, stage, i)
        # P3-002: confidence is no longer written to Qdrant payloads.
        # Postgres `memories.confidence` is the single source of truth and
        # is batch-fetched in retrieval/_apply_recency_weighting.
        payload = {
            "entity_id": point_id,
            "namespace": namespace,
            "source_stage": stage,
            "run_id": run_id,
            "importance": 5.0,
            "created_at": now,
            "text_preview": chunk.text[:200],
        }

        prefix = _COLLECTION_PREFIX[chunk.chunk_type]

        upsert_tasks.append(
            vector_store.upsert_dense(
                collection=f"{prefix}_dense",
                id=point_id,
                vector=vectors[i],
                payload=payload,
            )
        )
        upsert_tasks.append(
            vector_store.upsert_sparse(
                collection=f"{prefix}_sparse",
                id=point_id,
                text=chunk.text,
                payload=payload,
            )
        )

    await asyncio.gather(*upsert_tasks)

    artifacts = len(artifact_chunks)
    facts = len(fact_chunks)
    logger.info(
        "Indexed %d artifacts + %d facts for stage=%s run=%s",
        artifacts,
        facts,
        stage,
        run_id,
    )

    return IndexResult(
        artifacts_indexed=artifacts,
        facts_indexed=facts,
        total_chunks=artifacts + facts,
    )
