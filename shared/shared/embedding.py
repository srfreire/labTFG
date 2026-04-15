"""Voyage AI embeddings (asymmetric) + ZeroEntropy reranking."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import voyageai
from zeroentropy import ZeroEntropy

BATCH_SIZE = voyageai.VOYAGE_EMBED_BATCH_SIZE  # 128
DOC_EMBED_MODEL = "voyage-4-large"
QUERY_EMBED_MODEL = "voyage-4-lite"
ZERANK_MODEL = "zerank-2"
MAX_RETRIES = 3


@dataclass(frozen=True)
class RankedResult:
    index: int
    score: float
    document: str


class EmbeddingService:
    """Voyage AI embeddings + ZeroEntropy reranking."""

    def __init__(self, voyage_api_key: str, zeroentropy_api_key: str) -> None:
        self._embed_client = voyageai.AsyncClient(api_key=voyage_api_key, max_retries=MAX_RETRIES)
        self._rerank_client = ZeroEntropy(api_key=zeroentropy_api_key)

    async def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """Embed document texts with auto-batching using voyage-4-large."""
        if not texts:
            return []

        batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
        results = await asyncio.gather(
            *(
                self._embed_client.embed(batch, model=DOC_EMBED_MODEL, input_type="document")
                for batch in batches
            )
        )
        return [vec for r in results for vec in r.embeddings]

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single query text using voyage-4-lite for fast search."""
        result = await self._embed_client.embed(
            [query], model=QUERY_EMBED_MODEL, input_type="query"
        )
        if not result.embeddings:
            raise RuntimeError("Voyage AI returned no embedding for the query")
        return result.embeddings[0]

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 10,
    ) -> list[RankedResult]:
        """Rerank documents by relevance to query using zerank-2, sorted descending."""
        if not documents:
            return []

        response = self._rerank_client.models.rerank(
            model=ZERANK_MODEL,
            query=query,
            documents=documents,
        )
        ranked = sorted(response.results, key=lambda r: r.relevance_score, reverse=True)
        return [
            RankedResult(
                index=r.index,
                score=r.relevance_score,
                document=documents[r.index],
            )
            for r in ranked[:top_k]
        ]
