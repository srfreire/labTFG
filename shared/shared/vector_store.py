"""Async Qdrant client for dense and sparse vector storage."""
from __future__ import annotations

import logging

from qdrant_client import AsyncQdrantClient

from shared.settings import Settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Thin async wrapper around Qdrant."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.QDRANT_URL
        self._client: AsyncQdrantClient | None = None

    async def connect(self) -> None:
        """Open the client and verify connectivity."""
        client = AsyncQdrantClient(url=self._url)
        try:
            await client.get_collections()
        except Exception:
            await client.close()
            raise
        self._client = client
        logger.info("Connected to Qdrant at %s", self._url)

    async def close(self) -> None:
        """Close the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _c(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("VectorStore not connected — call connect() first")
        return self._client

    @property
    def client(self) -> AsyncQdrantClient:
        return self._c()
