"""P2-001 — happy-path test for ``simlab.knowledge.build_writer_from_services``.

This test lives in phase2-juan because it requires ``simlab`` to be importable.
"""

from __future__ import annotations

from types import SimpleNamespace

from simlab.knowledge import TrackerMemoryWriter, build_writer_from_services

from shared.services import Services


def test_build_writer_from_services_with_full_infra():
    """build_writer_from_services returns a TrackerMemoryWriter when infra is up."""
    fake_vectors = SimpleNamespace()
    fake_embeddings = SimpleNamespace()
    fake_db = SimpleNamespace()
    services = Services(
        db=fake_db,
        storage=SimpleNamespace(),
        kg=None,
        vectors=fake_vectors,
        embeddings=fake_embeddings,
    )

    writer = build_writer_from_services(services)

    assert isinstance(writer, TrackerMemoryWriter)
    # The writer holds the exact instances passed in — no new connections made.
    assert writer._vectors is fake_vectors
    assert writer._embeddings is fake_embeddings
    assert writer._db is fake_db


def test_build_writer_returns_none_when_vectors_missing():
    """No vectors → no writer."""
    services = Services(
        db=SimpleNamespace(),
        storage=SimpleNamespace(),
        kg=None,
        vectors=None,
        embeddings=SimpleNamespace(),
    )
    assert build_writer_from_services(services) is None


def test_build_writer_returns_none_when_embeddings_missing():
    """No embeddings → no writer."""
    services = Services(
        db=SimpleNamespace(),
        storage=SimpleNamespace(),
        kg=None,
        vectors=SimpleNamespace(),
        embeddings=None,
    )
    assert build_writer_from_services(services) is None
