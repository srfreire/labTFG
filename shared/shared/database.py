"""Async database service using SQLAlchemy 2.0."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.settings import Settings


class DatabaseService:
    def __init__(self, settings: Settings):
        self._dsn = settings.POSTGRES_DSN
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        self._engine = create_async_engine(
            self._dsn, pool_size=5, max_overflow=10
        )
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        # Verify connectivity
        async with self._engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        assert self._session_factory is not None, "Call connect() first"
        async with self._session_factory() as session:
            yield session
