"""Top-level pytest fixtures shared across integration and e2e tests.

All tests here target real docker-compose infrastructure — Postgres, Neo4j,
Qdrant, and MinIO. Mark them with @pytest.mark.integration or
@pytest.mark.e2e so CI can opt in/out.

The fixtures below give each test module a clean slate by creating/dropping
tables between runs and wiping managed Qdrant collections.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

# Load .env files from sibling projects so real-LLM and infra-coordinated tests
# pick up ANTHROPIC_*, VOYAGE_*, NEO4J_* keys without shell setup.
try:
    from dotenv import load_dotenv

    _ROOT = Path(__file__).resolve().parent.parent
    for env_path in (_ROOT / "shared" / ".env", _ROOT / "phase1-pablo" / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)
except ImportError:
    pass

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.database import DatabaseService
from shared.knowledge_graph import KnowledgeGraph
from shared.models import Base
from shared.services import Services, init_services, shutdown_services
from shared.settings import Settings, load_settings
from shared.storage import StorageService
from shared.vector_store import VectorStore

# ---------------------------------------------------------------------------
# Settings / DSNs
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def settings() -> Settings:
    return load_settings()


@pytest.fixture(scope="session")
def dsn(settings: Settings) -> str:
    return settings.POSTGRES_DSN


# ---------------------------------------------------------------------------
# Per-module DB lifecycle
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine(dsn: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(dsn)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess


# ---------------------------------------------------------------------------
# Connected services
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_service(settings: Settings, engine) -> AsyncIterator[DatabaseService]:
    """DatabaseService tied to the session's engine (table creation handled)."""
    db = DatabaseService(settings)
    await db.connect()
    yield db
    await db.close()


@pytest_asyncio.fixture
async def storage_service(settings: Settings) -> AsyncIterator[StorageService]:
    svc = StorageService(settings)
    await svc.connect()
    yield svc
    await svc.close()


@pytest_asyncio.fixture
async def kg_service(settings: Settings) -> AsyncIterator[KnowledgeGraph]:
    kg = KnowledgeGraph(
        settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD
    )
    await kg.init_schema()
    yield kg
    # clean up
    try:
        await kg.query("MATCH (n) DETACH DELETE n")
    finally:
        await kg.close()


@pytest_asyncio.fixture
async def vector_store(settings: Settings) -> AsyncIterator[VectorStore]:
    vs = VectorStore(settings)
    await vs.connect()
    import contextlib

    client = vs._c()
    # Wipe managed collections so tests start from a clean state
    for name in ("memories_dense", "memories_sparse"):
        with contextlib.suppress(Exception):
            await client.delete_collection(name)
    await vs.init_collections()
    yield vs
    await vs.close()


# ---------------------------------------------------------------------------
# Services lifecycle (replaces the legacy shared.init/shutdown shim)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def services(settings: Settings) -> AsyncIterator[Services]:
    """Boots a ``Services`` via ``init_services``, tears down on exit."""
    svc = await init_services(settings)
    try:
        yield svc
    finally:
        await shutdown_services(svc)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def unique_prefix() -> str:
    """A unique S3 key prefix for cleanup-friendly test data."""
    return f"_xs/{uuid.uuid4().hex}/"


@pytest.fixture
def run_id() -> str:
    """A fresh UUID string suitable for scoping test artifacts."""
    return str(uuid.uuid4())
