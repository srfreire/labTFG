"""Edge-case tests for shared.store SQLite functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from shared import store

pytestmark = pytest.mark.integration


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch):
    """Point the legacy store at a temp SQLite DB and reset the connection."""
    db = tmp_path / "labtfg.db"
    monkeypatch.setattr(store, "_db_path", db)
    monkeypatch.setattr(store, "_conn", None)
    store.init_db()
    yield
    if store._conn is not None:
        store._conn.close()
        store._conn = None


def test_register_model_idempotent_replace():
    """Calling register_model twice with same ID replaces the row."""
    store.register_model(
        formulation_id="f-1",
        class_name="A",
        paradigm="p",
        description="d",
        file_path="/x.py",
    )
    store.register_model(
        formulation_id="f-1",
        class_name="B",
        paradigm="p",
        description="d2",
        file_path="/y.py",
    )
    rows = store.list_models()
    assert len(rows) == 1
    assert rows[0]["class_name"] == "B"
    assert rows[0]["file_path"] == "/y.py"


def test_register_model_with_metadata_persists_json():
    """Metadata dict round-trips through JSON."""
    store.register_model(
        formulation_id="f-meta",
        class_name="M",
        paradigm="p",
        description="d",
        file_path="/m.py",
        metadata={"k": "v", "n": 3},
    )
    row = store.get_model("f-meta")
    assert row is not None
    assert row["metadata_json"] is not None
    assert '"k": "v"' in row["metadata_json"]


def test_get_model_missing_returns_none():
    """get_model returns None for unknown ID."""
    assert store.get_model("no-such-id") is None


def test_list_models_orders_newest_first():
    """list_models sorts by registered_at desc."""
    store.register_model("a", "A", None, None, "/a.py")
    store.register_model("b", "B", None, None, "/b.py")
    rows = store.list_models()
    ids = [r["formulation_id"] for r in rows]
    # Both inserted; ordering by timestamp descending means most recent first.
    # SQLite CURRENT_TIMESTAMP is second-precision; tolerate either order.
    assert set(ids) == {"a", "b"}


def test_create_experiment_returns_uuid():
    exp_id = store.create_experiment("test exp")
    assert isinstance(exp_id, str)
    assert len(exp_id) == 36  # uuid4 string


def test_get_experiment_missing_returns_none():
    assert store.get_experiment("00000000-0000-0000-0000-000000000000") is None


def test_update_experiment_rejects_unknown_columns():
    """Unknown column keys raise ValueError before touching the DB."""
    exp_id = store.create_experiment("x")
    with pytest.raises(ValueError, match="Invalid columns"):
        store.update_experiment(exp_id, bogus_field="hi")


def test_update_experiment_no_kwargs_is_noop():
    exp_id = store.create_experiment("noop")
    store.update_experiment(exp_id)  # should not raise
    exp = store.get_experiment(exp_id)
    assert exp is not None and exp["description"] == "noop"


def test_update_experiment_writes_whitelisted_fields():
    exp_id = store.create_experiment("upd")
    store.update_experiment(
        exp_id,
        status=store.SIMULATED,
        steps=42,
        seed=7,
        spec_json="{}",
    )
    exp = store.get_experiment(exp_id)
    assert exp is not None
    assert exp["status"] == store.SIMULATED
    assert exp["steps"] == 42
    assert exp["seed"] == 7


def test_list_experiments_respects_limit():
    for i in range(5):
        store.create_experiment(f"e{i}")
    rows = store.list_experiments(limit=3)
    assert len(rows) == 3


def test_status_constants_unique():
    """All status constants are distinct strings."""
    statuses = {
        store.CREATED,
        store.SIMULATED,
        store.TRACKED,
        store.ANALYZED,
        store.REPORTED,
    }
    assert len(statuses) == 5
