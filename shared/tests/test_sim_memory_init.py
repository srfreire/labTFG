"""P2-001 — unit tests for `shared._init_sim_memory_writer` (no infra required).

The happy-path test (flag on + real TrackerMemoryWriter) lives in
`phase2-juan/tests/test_sim_memory_init.py` because `simlab` is only installed
in that package's environment. Here we cover the failure/short-circuit paths
that don't require the `simlab` import to succeed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import shared
from shared.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure sim_memory_writer is reset between tests (other globals untouched)."""
    shared.sim_memory_writer = None
    yield
    shared.sim_memory_writer = None


def _settings(enabled: bool) -> Settings:
    return Settings(
        VOYAGE_API_KEY="v",
        ZEROENTROPY_API_KEY="z",
        ENABLE_KNOWLEDGE_WRITE=enabled,
    )


def test_flag_off_leaves_writer_none(monkeypatch):
    # Populate infra globals with sentinels so we can confirm they aren't touched.
    monkeypatch.setattr(shared, "vectors", SimpleNamespace(), raising=False)
    monkeypatch.setattr(shared, "embeddings", SimpleNamespace(), raising=False)
    monkeypatch.setattr(shared, "db", SimpleNamespace(), raising=False)

    shared._init_sim_memory_writer(_settings(False))
    assert shared.sim_memory_writer is None


@pytest.mark.parametrize(
    "missing",
    ["vectors", "embeddings", "db"],
)
def test_flag_on_without_infra_logs_warning_and_skips(monkeypatch, caplog, missing):
    monkeypatch.setattr(
        shared,
        "vectors",
        None if missing == "vectors" else SimpleNamespace(),
        raising=False,
    )
    monkeypatch.setattr(
        shared,
        "embeddings",
        None if missing == "embeddings" else SimpleNamespace(),
        raising=False,
    )
    monkeypatch.setattr(
        shared,
        "db",
        None if missing == "db" else SimpleNamespace(),
        raising=False,
    )

    with caplog.at_level("WARNING", logger="shared"):
        shared._init_sim_memory_writer(_settings(True))

    assert shared.sim_memory_writer is None
    assert any("infra missing" in r.message for r in caplog.records)


def test_flag_on_with_bad_import_logs_and_skips(monkeypatch, caplog):
    monkeypatch.setattr(shared, "vectors", SimpleNamespace(), raising=False)
    monkeypatch.setattr(shared, "embeddings", SimpleNamespace(), raising=False)
    monkeypatch.setattr(shared, "db", SimpleNamespace(), raising=False)

    # Simulate `simlab.knowledge` not being on the path.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "simlab.knowledge":
            raise ImportError("simlab not installed here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with caplog.at_level("WARNING", logger="shared"):
        shared._init_sim_memory_writer(_settings(True))

    assert shared.sim_memory_writer is None
    assert any("simlab.knowledge import failed" in r.message for r in caplog.records)
