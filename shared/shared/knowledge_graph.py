"""Async Neo4j client for the knowledge graph."""
from __future__ import annotations

import logging

from neo4j import AsyncGraphDatabase, AsyncDriver

from shared.settings import Settings

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Thin async wrapper around Neo4j's async driver."""

    def __init__(self, settings: Settings) -> None:
        self._uri = settings.NEO4J_URI
        self._user = settings.NEO4J_USER
        self._password = settings.NEO4J_PASSWORD
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Open the driver and verify connectivity."""
        driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        try:
            await driver.verify_connectivity()
        except Exception:
            await driver.close()
            raise
        self._driver = driver
        logger.info("Connected to Neo4j at %s", self._uri)

    async def close(self) -> None:
        """Close the driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    def _d(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("KnowledgeGraph not connected — call connect() first")
        return self._driver

    @property
    def driver(self) -> AsyncDriver:
        return self._d()
