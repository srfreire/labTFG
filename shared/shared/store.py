"""Experiment Store — SQLite persistence for the simulation lab."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk up from cwd to find the repo root (contains CLAUDE.md)."""
    p = Path.cwd().resolve()
    for parent in [p, *p.parents]:
        if (parent / "CLAUDE.md").exists():
            return parent
    return p


_db_path: Path = _find_repo_root() / "data" / "labtfg.db"

_EXPERIMENT_COLUMNS = frozenset(
    {
        "description",
        "status",
        "spec_json",
        "models_used",
        "steps",
        "seed",
        "events_json",
        "replay_json",
        "tracker_json",
        "analyst_json",
        "pdf_path",
    }
)

# Status constants
CREATED = "created"
SIMULATED = "simulated"
TRACKED = "tracked"
ANALYZED = "analyzed"
REPORTED = "reported"

# Persistent connection (lazy init)
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None or _db_path != getattr(_get_conn, "_path", None):
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _get_conn._path = _db_path  # type: ignore[attr-defined]
    return _conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            formulation_id  TEXT PRIMARY KEY,
            class_name      TEXT NOT NULL,
            paradigm        TEXT,
            description     TEXT,
            file_path       TEXT NOT NULL,
            registered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata_json   TEXT
        );
        CREATE TABLE IF NOT EXISTS experiments (
            id              TEXT PRIMARY KEY,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description     TEXT,
            status          TEXT DEFAULT 'created',
            spec_json       TEXT,
            models_used     TEXT,
            steps           INTEGER,
            seed            INTEGER,
            events_json     TEXT,
            replay_json     TEXT,
            tracker_json    TEXT,
            analyst_json    TEXT,
            pdf_path        TEXT
        );
    """)


# ---------------------------------------------------------------------------
# Models (prepared for Phase 1)
# ---------------------------------------------------------------------------


def register_model(
    formulation_id: str,
    class_name: str,
    paradigm: str | None,
    description: str | None,
    file_path: str,
    metadata: dict | None = None,
) -> None:
    """Register a decision model. Idempotent (INSERT OR REPLACE)."""
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO models
           (formulation_id, class_name, paradigm, description, file_path, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            formulation_id,
            class_name,
            paradigm,
            description,
            file_path,
            json.dumps(metadata) if metadata else None,
        ),
    )
    conn.commit()


def list_models() -> list[dict]:
    """Return all registered models, newest first."""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM models ORDER BY registered_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_model(formulation_id: str) -> dict | None:
    """Return a single model by ID, or None if not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM models WHERE formulation_id = ?", (formulation_id,)
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Experiments (Phase 2)
# ---------------------------------------------------------------------------


def create_experiment(description: str) -> str:
    """Create a new experiment. Returns the UUID."""
    exp_id = str(uuid.uuid4())
    conn = _get_conn()
    conn.execute(
        "INSERT INTO experiments (id, description) VALUES (?, ?)",
        (exp_id, description),
    )
    conn.commit()
    return exp_id


def update_experiment(experiment_id: str, **kwargs: object) -> None:
    """Update experiment columns. Validates keys against whitelist."""
    invalid = set(kwargs) - _EXPERIMENT_COLUMNS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    if not kwargs:
        return
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values())
    conn = _get_conn()
    conn.execute(
        f"UPDATE experiments SET {cols}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        [*vals, experiment_id],
    )
    conn.commit()


def get_experiment(experiment_id: str) -> dict | None:
    """Return a single experiment by ID, or None if not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
    ).fetchone()
    return dict(row) if row else None


def list_experiments(limit: int = 20) -> list[dict]:
    """Return the most recent experiments, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM experiments ORDER BY rowid DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
