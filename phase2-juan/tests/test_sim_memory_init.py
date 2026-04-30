"""P2-001 — happy-path test for `shared._init_sim_memory_writer`.

This test lives in phase2-juan (not shared) because it requires `simlab` to be
importable. Shared's test suite covers the failure/short-circuit paths.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simlab.knowledge import TrackerMemoryWriter

import shared
from shared.settings import Settings


@pytest.fixture(autouse=True)
def _reset_singleton():
    shared.sim_memory_writer = None
    yield
    shared.sim_memory_writer = None


def test_flag_on_with_infra_creates_tracker_memory_writer(monkeypatch):
    fake_vectors = SimpleNamespace()
    fake_embeddings = SimpleNamespace()
    fake_db = SimpleNamespace()
    monkeypatch.setattr(shared, "vectors", fake_vectors, raising=False)
    monkeypatch.setattr(shared, "embeddings", fake_embeddings, raising=False)
    monkeypatch.setattr(shared, "db", fake_db, raising=False)

    settings = Settings(
        VOYAGE_API_KEY="v",
        ZEROENTROPY_API_KEY="z",
        ENABLE_KNOWLEDGE_WRITE=True,
    )
    shared._init_sim_memory_writer(settings)

    writer = shared.sim_memory_writer
    assert isinstance(writer, TrackerMemoryWriter)
    # The writer holds the exact instances passed in — no new connections made.
    assert writer._vectors is fake_vectors
    assert writer._embeddings is fake_embeddings
    assert writer._db is fake_db
