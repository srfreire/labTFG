"""Tests for the chat_messages table, ChatMessage ORM model, and
ENABLE_CHAT_PERSISTENCE flag (sim-recall P2-001).

Unit tests cover ORM column shape and the settings flag.
Integration tests apply/revert the Alembic migration against a live
Postgres (requires docker-compose Postgres on localhost:5432).
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# AC3 — ChatMessage class exists with the expected columns
# ---------------------------------------------------------------------------


def test_chat_message_import_and_columns():
    from shared.models import ChatMessage

    cols = {c.name: c for c in ChatMessage.__table__.columns}
    assert {"id", "session_id", "experiment_id", "role", "content", "tool_name",
            "created_at"} <= set(cols)
    assert cols["id"].primary_key
    assert not cols["session_id"].nullable
    assert cols["experiment_id"].nullable
    assert not cols["role"].nullable
    assert not cols["content"].nullable
    assert cols["tool_name"].nullable
    # experiment_id FK targets experiments.id with SET NULL on delete
    fks = list(cols["experiment_id"].foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "experiments"
    assert fks[0].ondelete == "SET NULL"


def test_chat_message_id_column_has_uuid_default():
    from shared.models import ChatMessage

    col = ChatMessage.__table__.columns["id"]
    assert col.default is not None
    assert col.default.is_callable
    assert col.default.arg.__name__ == "uuid4"


def test_chat_message_indexes_declared():
    from shared.models import ChatMessage

    names = {idx.name for idx in ChatMessage.__table__.indexes}
    assert {
        "ix_chat_messages_session",
        "ix_chat_messages_experiment",
        "ix_chat_messages_created",
    } <= names


# ---------------------------------------------------------------------------
# AC4 — ENABLE_CHAT_PERSISTENCE flag default + env override
# ---------------------------------------------------------------------------


def test_settings_flag_default_false():
    from shared.settings import Settings

    assert Settings().ENABLE_CHAT_PERSISTENCE is False


def test_settings_flag_env_override(monkeypatch):
    from shared.settings import load_settings

    monkeypatch.setenv("ENABLE_CHAT_PERSISTENCE", "true")
    assert load_settings().ENABLE_CHAT_PERSISTENCE is True

    monkeypatch.setenv("ENABLE_CHAT_PERSISTENCE", "0")
    assert load_settings().ENABLE_CHAT_PERSISTENCE is False


# ---------------------------------------------------------------------------
# Migration module sanity (no live DB needed)
# ---------------------------------------------------------------------------


def test_migration_links_to_prev_head():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "e271a24ca95c_add_chat_messages_table.py"
    )
    spec = importlib.util.spec_from_file_location("chat_messages_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "e271a24ca95c"
    assert migration.down_revision == "e7a4c9d2b813"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


# ---------------------------------------------------------------------------
# AC1 / AC2 — live Alembic upgrade/downgrade against a real Postgres
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_alembic_upgrade_creates_table_and_indexes(tmp_path):
    """``alembic upgrade head`` applies cleanly and creates the table + 3 indexes."""
    from sqlalchemy import create_engine, inspect

    from shared.settings import load_settings

    sync_dsn = load_settings().POSTGRES_DSN.replace("+asyncpg", "")
    engine = create_engine(sync_dsn)

    _alembic_upgrade("head")

    with engine.connect() as conn:
        insp = inspect(conn)
        assert "chat_messages" in insp.get_table_names()
        idx_names = {i["name"] for i in insp.get_indexes("chat_messages")}
        assert {
            "ix_chat_messages_session",
            "ix_chat_messages_experiment",
            "ix_chat_messages_created",
        } <= idx_names


@pytest.mark.integration
def test_alembic_downgrade_drops_table():
    from sqlalchemy import create_engine, inspect

    from shared.settings import load_settings

    sync_dsn = load_settings().POSTGRES_DSN.replace("+asyncpg", "")
    engine = create_engine(sync_dsn)

    _alembic_upgrade("head")
    _alembic_downgrade("-1")

    with engine.connect() as conn:
        insp = inspect(conn)
        assert "chat_messages" not in insp.get_table_names()

    # Restore head for subsequent tests
    _alembic_upgrade("head")


def _alembic_upgrade(target: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).parent.parent / "migrations")
    )
    command.upgrade(cfg, target)


def _alembic_downgrade(target: str) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).parent.parent / "migrations")
    )
    command.downgrade(cfg, target)
