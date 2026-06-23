"""End-to-end tests for query_history against a real test DB (sim-recall P3-004).

Seeds a tmp schema (Base.metadata.create_all) with a handful of
experiments, chat_messages, and pipeline_memories rows, then drives
query_history through three NL-style questions with the LLM planner
mocked. Asserts the returned markdown has the expected headers and rows.

Gated by ``pytest.mark.integration`` since it requires Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from simlab.nlsql import query_history
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.database import DatabaseService
from shared.models import (
    Base,
    ChatMessage,
    Experiment,
    PipelineMemory,
    Run,
)
from shared.settings import Settings, load_settings

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def seeded_db():
    """Spin up a clean schema and seed minimal fixtures."""
    dsn = load_settings().POSTGRES_DSN
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    run_id = uuid.uuid4()
    exp_a = uuid.uuid4()
    exp_b = uuid.uuid4()
    session_id = uuid.uuid4()

    async with factory() as session:
        session.add_all(
            [
                Run(
                    id=run_id,
                    problem_description="seed run",
                    s3_prefix="runs/seed/",
                ),
                Experiment(
                    id=exp_a,
                    description="prospect theory comparison",
                    status="reported",
                ),
                Experiment(
                    id=exp_b,
                    description="homeostatic baseline",
                    status="analyzed",
                ),
                ChatMessage(
                    session_id=session_id,
                    role="user",
                    content="¿qué pasó con prospect theory?",
                ),
                ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content="ran the simulation",
                ),
                ChatMessage(
                    session_id=session_id,
                    role="user",
                    content="otra pregunta",
                ),
                PipelineMemory(
                    content="prospect theory paradigm postulate",
                    namespace="paradigm",
                    memory_type="semantic",
                    source_stage="researcher",
                    run_id=run_id,
                    importance=0.8,
                    confidence=0.9,
                    valid_from=datetime.now(),
                ),
                PipelineMemory(
                    content="homeostatic paradigm postulate",
                    namespace="paradigm",
                    memory_type="semantic",
                    source_stage="researcher",
                    run_id=run_id,
                    importance=0.7,
                    confidence=0.85,
                    valid_from=datetime.now(),
                ),
            ]
        )
        await session.commit()

    db = DatabaseService(Settings(POSTGRES_DSN=dsn))
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


# ---------------------------------------------------------------------------
# AC4 — three planned queries return markdown with expected headers/rows
# ---------------------------------------------------------------------------


async def test_query_history_over_experiments(seeded_db):
    sql = "SELECT description, status FROM experiments ORDER BY description"
    with patch("simlab.nlsql._plan", new=AsyncMock(return_value={"sql": sql})):
        out = await query_history("dame todos los experimentos", db=seeded_db)

    assert "| description | status |" in out
    assert "homeostatic baseline" in out
    assert "prospect theory comparison" in out


async def test_query_history_over_chat_messages(seeded_db):
    sql = "SELECT role, content FROM chat_messages WHERE role='user' ORDER BY content"
    with patch("simlab.nlsql._plan", new=AsyncMock(return_value={"sql": sql})):
        out = await query_history("¿qué le pregunté?", db=seeded_db)

    assert "| role | content |" in out
    assert "prospect theory" in out
    assert "otra pregunta" in out


async def test_query_history_over_pipeline_memories(seeded_db):
    sql = (
        "SELECT namespace, content FROM pipeline_memories "
        "WHERE namespace='paradigm' ORDER BY content"
    )
    with patch("simlab.nlsql._plan", new=AsyncMock(return_value={"sql": sql})):
        out = await query_history("qué paradigmas hemos investigado", db=seeded_db)

    assert "| namespace | content |" in out
    # both paradigms should be visible
    assert "homeostatic" in out
    assert "prospect theory" in out
