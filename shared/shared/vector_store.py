"""Async Qdrant client for dense + sparse vector operations."""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    PointStruct,
    Range,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from shared.settings import Settings

BM25_MODEL = "Qdrant/bm25"

COLLECTIONS_DENSE = {
    "artifacts_dense": 1024,
    "memories_dense": 1024,
}

COLLECTIONS_SPARSE = [
    "artifacts_sparse",
    "memories_sparse",
]


@dataclass(frozen=True)
class ScoredPoint:
    id: str
    score: float
    payload: dict


class VectorStore:
    """Thin async wrapper around Qdrant for dense + sparse vector operations."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.QDRANT_URL
        self._client: AsyncQdrantClient | None = None

    # -- lifecycle -------------------------------------------------------------

    async def connect(self) -> None:
        """Create the async Qdrant client."""
        self._client = AsyncQdrantClient(url=self._url)

    async def init_collections(self) -> None:
        """Create all 4 collections if they don't already exist (idempotent).

        Sparse collections use ``Modifier.IDF`` so Qdrant applies BM25's
        IDF weighting server-side; tokenization happens client-side via
        FastEmbed's ``Qdrant/bm25`` model.
        """
        client = self._c()
        existing = {c.name for c in (await client.get_collections()).collections}

        for name, dim in COLLECTIONS_DENSE.items():
            if name not in existing:
                await client.create_collection(
                    collection_name=name,
                    vectors_config={
                        "dense": VectorParams(size=dim, distance=Distance.COSINE)
                    },
                )

        for name in COLLECTIONS_SPARSE:
            if name not in existing:
                await client.create_collection(
                    collection_name=name,
                    vectors_config={},
                    sparse_vectors_config={
                        "sparse": SparseVectorParams(
                            index=SparseIndexParams(),
                            modifier=Modifier.IDF,
                        ),
                    },
                )

    async def close(self) -> None:
        """Close the async Qdrant client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _c(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("VectorStore not connected — call connect() first")
        return self._client

    # -- public API ------------------------------------------------------------

    async def upsert_dense(
        self,
        collection: str,
        id: str,
        vector: list[float],
        payload: dict,
    ) -> None:
        """Upsert a single dense vector with payload."""
        await self._c().upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=id,
                    vector={"dense": vector},
                    payload=payload,
                ),
            ],
        )

    async def upsert_sparse(
        self,
        collection: str,
        id: str,
        text: str,
        payload: dict,
    ) -> None:
        """Upsert a single sparse point from raw text.

        FastEmbed tokenizes client-side; Qdrant applies BM25 with IDF
        server-side.
        """
        await self._c().upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=id,
                    vector={"sparse": Document(text=text, model=BM25_MODEL)},
                    payload=payload,
                ),
            ],
        )

    async def search_dense(
        self,
        collection: str,
        vector: list[float],
        limit: int = 20,
        filters: dict | None = None,
    ) -> list[ScoredPoint]:
        """Search a dense collection by vector similarity."""
        results = await self._c().query_points(
            collection_name=collection,
            query=vector,
            using="dense",
            limit=limit,
            query_filter=_build_filter(filters) if filters else None,
        )
        return [
            ScoredPoint(id=str(p.id), score=p.score, payload=p.payload or {})
            for p in results.points
        ]

    async def search_sparse(
        self,
        collection: str,
        query: str,
        limit: int = 20,
        filters: dict | None = None,
    ) -> list[ScoredPoint]:
        """Search a sparse collection by BM25 over raw query text.

        FastEmbed tokenizes client-side; Qdrant scores with BM25 + IDF
        server-side.
        """
        results = await self._c().query_points(
            collection_name=collection,
            query=Document(text=query, model=BM25_MODEL),
            using="sparse",
            limit=limit,
            query_filter=_build_filter(filters) if filters else None,
        )
        return [
            ScoredPoint(id=str(p.id), score=p.score, payload=p.payload or {})
            for p in results.points
        ]

    async def set_payload(
        self,
        collection: str,
        id: str,
        payload: dict,
    ) -> None:
        """Update payload fields on an existing point (merge, not replace)."""
        await self._c().set_payload(
            collection_name=collection,
            payload=payload,
            points=[id],
        )

    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete points by their IDs."""
        await self._c().delete(
            collection_name=collection,
            points_selector=ids,
        )


# -- helpers -------------------------------------------------------------------


def _build_filter(filters: dict) -> Filter:
    """Convert a flat dict of filters to Qdrant Filter objects.

    Supported forms:
        {"namespace": "paradigm"}             → exact match
        {"confidence": {"gte": 0.7}}          → range filter
    """
    conditions = []
    for key, value in filters.items():
        if isinstance(value, dict):
            conditions.append(FieldCondition(key=key, range=Range(**value)))
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)
