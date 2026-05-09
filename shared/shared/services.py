"""Services context — explicit dependency container for shared infrastructure.

Replaces the module-level globals that used to live in ``shared/__init__.py``
(``shared.kg``, ``shared.vectors``, ``shared.embeddings``, ``shared.db``,
``shared.storage``, ``shared.sim_memory_writer``). Entry points (FastAPI
lifespan handlers, CLI commands, eval harness, scripts) call
``init_services(settings)`` once at boot, thread the returned ``Services``
through every consumer that needs infra, and call
``shutdown_services(services)`` on exit.

Tests construct ``Services`` directly with fakes — no monkeypatching seams,
no global mutation.

The ``sim_memory_writer`` field is intentionally typed ``object | None`` to
avoid an import of ``simlab`` from ``shared`` (the Phase 1 ↔ Phase 2 import
cycle that motivated this refactor). Phase 2 entry points construct their
writer separately and replace the field via ``dataclasses.replace``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from shared.database import DatabaseService
from shared.embedding import EmbeddingService
from shared.knowledge_graph import KnowledgeGraph
from shared.settings import Settings, load_settings
from shared.storage import StorageService
from shared.vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Services:
    """Bundle of infrastructure services constructed from ``Settings``.

    ``db`` and ``storage`` are required (Postgres / MinIO are core
    dependencies of every entry point). ``kg``, ``vectors`` and
    ``embeddings`` are optional — each component degrades independently and
    will be ``None`` if its backing service or credentials are unavailable.

    ``sim_memory_writer`` is a Phase 2 concept; it is left ``None`` by
    ``init_services`` and populated by Phase 2 entry points via
    ``dataclasses.replace(services, sim_memory_writer=...)``.
    """

    db: DatabaseService
    storage: StorageService
    kg: KnowledgeGraph | None = None
    vectors: VectorStore | None = None
    embeddings: EmbeddingService | None = None
    sim_memory_writer: object | None = None


async def init_services(settings: Settings | None = None) -> Services:
    """Boot all infrastructure services and return an immutable ``Services``.

    Postgres and MinIO are required. Knowledge infrastructure (Neo4j,
    Qdrant, Voyage AI / ZeroEntropy embeddings) degrades independently —
    each component logs a warning and is left ``None`` on failure.
    """
    if settings is None:
        settings = load_settings()

    storage = StorageService(settings)
    await storage.connect()

    db = DatabaseService(settings)
    await db.connect()

    kg: KnowledgeGraph | None = None
    vectors: VectorStore | None = None
    embeddings: EmbeddingService | None = None
    unavailable: list[str] = []

    try:
        _kg = KnowledgeGraph(
            settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD
        )
        await _kg.init_schema()
        kg = _kg
    except Exception:
        logger.warning("Neo4j unavailable — KnowledgeGraph disabled", exc_info=True)
        unavailable.append("Neo4j")

    try:
        _vs = VectorStore(settings)
        await _vs.connect()
        await _vs.init_collections()
        vectors = _vs
    except Exception:
        logger.warning("Qdrant unavailable — VectorStore disabled", exc_info=True)
        unavailable.append("Qdrant")

    if settings.VOYAGE_API_KEY and settings.ZEROENTROPY_API_KEY:
        embeddings = EmbeddingService(
            settings.VOYAGE_API_KEY, settings.ZEROENTROPY_API_KEY
        )
    else:
        missing = [
            k
            for k in ("VOYAGE_API_KEY", "ZEROENTROPY_API_KEY")
            if not getattr(settings, k)
        ]
        unavailable.append(f"Voyage AI ({', '.join(missing)})")

    if unavailable:
        logger.warning(
            "Knowledge infrastructure unavailable: %s. Running in degraded mode.",
            ", ".join(unavailable),
        )

    return Services(
        db=db,
        storage=storage,
        kg=kg,
        vectors=vectors,
        embeddings=embeddings,
    )


async def shutdown_services(services: Services) -> None:
    """Tear down every connected service in ``services``.

    Idempotent: safe to call on a partially-constructed ``Services`` (e.g.
    if ``init_services`` was interrupted mid-boot). The caller does not need
    to clear references — ``Services`` is frozen, so the caller drops it.
    """
    if services.storage is not None:
        await services.storage.close()
    if services.db is not None:
        await services.db.close()
    if services.kg is not None:
        await services.kg.close()
    if services.vectors is not None:
        await services.vectors.close()


__all__ = [
    "Services",
    "init_services",
    "replace",
    "shutdown_services",
]
