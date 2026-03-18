"""Tests for shared.store — Experiment Store persistence."""
import sqlite3

import pytest
from shared.store import (
    init_db, _db_path, _conn,
    register_model, list_models, get_model,
    create_experiment, update_experiment, get_experiment, list_experiments,
    CREATED, SIMULATED, TRACKED, ANALYZED, REPORTED,
)
import shared.store as store_mod


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """Isolate each test with a fresh DB."""
    monkeypatch.setattr("shared.store._db_path", tmp_path / "test.db")
    monkeypatch.setattr("shared.store._conn", None)
    init_db()
    return tmp_path / "test.db"


# --- Init ---

def test_init_db_creates_tables(db):
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "models" in tables
    assert "experiments" in tables


def test_init_db_is_idempotent():
    init_db()  # Should not raise (already called by fixture)


# --- Model CRUD ---

def test_register_and_get_model():
    register_model(
        formulation_id="test_model",
        class_name="TestModel",
        paradigm="test",
        description="A test model",
        file_path="path/to/model.py",
    )
    model = get_model("test_model")
    assert model is not None
    assert model["class_name"] == "TestModel"
    assert model["paradigm"] == "test"


def test_register_model_is_idempotent():
    register_model("m1", "C1", "p1", "desc", "path.py")
    register_model("m1", "C1_updated", "p1", "desc", "path.py")
    model = get_model("m1")
    assert model["class_name"] == "C1_updated"


def test_list_models():
    register_model("m1", "C1", "p1", "d1", "p1.py")
    register_model("m2", "C2", "p2", "d2", "p2.py")
    models = list_models()
    assert len(models) == 2
    ids = {m["formulation_id"] for m in models}
    assert ids == {"m1", "m2"}


def test_get_model_not_found():
    assert get_model("nonexistent") is None


# --- Experiment CRUD ---

def test_create_and_get_experiment():
    exp_id = create_experiment(description="test experiment")
    assert isinstance(exp_id, str)
    assert len(exp_id) == 36  # UUID format

    exp = get_experiment(exp_id)
    assert exp is not None
    assert exp["description"] == "test experiment"
    assert exp["status"] == CREATED


def test_update_experiment():
    exp_id = create_experiment(description="test")
    update_experiment(exp_id, status=SIMULATED, steps=30, seed=42)

    exp = get_experiment(exp_id)
    assert exp["status"] == SIMULATED
    assert exp["steps"] == 30
    assert exp["seed"] == 42


def test_update_experiment_rejects_invalid_column():
    exp_id = create_experiment(description="test")
    with pytest.raises(ValueError, match="Invalid columns"):
        update_experiment(exp_id, invalid_column="bad")


def test_list_experiments_ordered_by_date():
    id1 = create_experiment(description="first")
    id2 = create_experiment(description="second")
    exps = list_experiments()
    assert len(exps) == 2
    assert exps[0]["id"] == id2  # Most recent first
    assert exps[1]["id"] == id1


def test_list_experiments_respects_limit():
    for i in range(5):
        create_experiment(description=f"exp {i}")
    exps = list_experiments(limit=3)
    assert len(exps) == 3


def test_get_experiment_not_found():
    assert get_experiment("nonexistent") is None


# --- Status constants ---

def test_status_constants():
    assert CREATED == "created"
    assert SIMULATED == "simulated"
    assert TRACKED == "tracked"
    assert ANALYZED == "analyzed"
    assert REPORTED == "reported"
