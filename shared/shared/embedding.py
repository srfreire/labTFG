"""Voyage AI embedding and reranking client with auto-batching."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import voyageai

BATCH_SIZE = voyageai.VOYAGE_EMBED_BATCH_SIZE  # 128
EMBED_MODEL = "voyage-3"
RERANK_MODEL = "rerank-2"
MAX_RETRIES = 3


@dataclass(frozen=True)
class RankedResult:
    index: int
    score: float
    document: str


class EmbeddingService:
    """Async wrapper around Voyage AI for embeddings and reranking."""

    def __init__(self, api_key: str) -> None:
        self._client = voyageai.AsyncClient(api_key=api_key, max_retries=MAX_RETRIES)

    async def embed_texts(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> list[list[float]]:
        """Embed texts with auto-batching (128 per request)."""
        if not texts:
            return []

        batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
        results = await asyncio.gather(
            *(
                self._client.embed(batch, model=EMBED_MODEL, input_type=input_type)
                for batch in batches
            )
        )
        return [vec for r in results for vec in r.embeddings]

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query text optimized for search."""
        vectors = await self.embed_texts([query], input_type="query")
        if not vectors:
            raise RuntimeError("Voyage AI returned no embedding for the query")
        return vectors[0]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
    ) -> list[RankedResult]:
        """Rerank documents by relevance to query, sorted descending."""
        if not documents:
            return []

        result = await self._client.rerank(
            query=query,
            documents=documents,
            model=RERANK_MODEL,
            top_k=top_k,
        )
        return [
            RankedResult(
                index=r.index,
                score=r.relevance_score,
                document=r.document,
            )
            for r in result.results
        ]
