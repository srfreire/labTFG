"""Tests for Router agrex.Tracer lifecycle (_init_trace, _finalize_trace).

Per-stage tracer call coverage is exercised in test_router_*.py — this
file covers the lifecycle scaffolding only.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import agrex
import pytest

from decisionlab.router import PipelineState, Router, Stage
from shared.services import Services


def _make_services(*, storage=None) -> Services:
    return Services(
        db=MagicMock(),
        storage=storage if storage is not None else MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )


def _make_router(*, services=None) -> Router:
    """Construct a Router with minimal init for lifecycle testing."""
    state = PipelineState(
        stage=Stage.RESEARCH,
        problem="test problem",
        reports_dir=Path("."),
        run_id="test-run-id",
    )
    services = services or _make_services()
    with patch.object(Router, "_init_memory_agent", return_value=None):
        return Router(
            client=AsyncMock(),
            state=state,
            search=MagicMock(),
            project_root=Path("."),
            services=services,
        )


def test_init_trace_creates_local_file():
    router = _make_router()
    router._init_trace("test-run-id")
    try:
        assert router._tracer is not None
        assert isinstance(router._tracer, agrex.Tracer)
        assert router._trace_local_path is not None
        assert router._trace_local_path.exists()
    finally:
        if router._tracer is not None:
            router._tracer.close()
        if router._trace_local_path is not None:
            router._trace_local_path.unlink(missing_ok=True)


def test_init_trace_replaces_prior_tracer():
    router = _make_router()
    router._init_trace("run-1")
    first = router._tracer
    first_path = router._trace_local_path
    router._init_trace("run-2")
    try:
        assert router._tracer is not first
        assert router._trace_local_path != first_path
        assert first_path is not None and not first_path.exists()
    finally:
        if router._tracer is not None:
            router._tracer.close()
        if router._trace_local_path is not None:
            router._trace_local_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_finalize_trace_uploads_to_s3():
    fake_storage = MagicMock()
    fake_storage.put_text = AsyncMock()
    services = _make_services(storage=fake_storage)
    router = _make_router(services=services)
    router._init_trace("test-run-id")
    router._tracer.agent("a", "A")
    router._tracer.done("a")

    await router._finalize_trace("test-run-id")

    fake_storage.put_text.assert_awaited_once()
    key, content = fake_storage.put_text.call_args.args
    assert key == "research/test-run-id/trace.jsonl"
    assert content.count("\n") == 2
    assert '"type": "node_add"' in content
    assert '"type": "node_update"' in content
    assert router._tracer is None
    assert router._trace_local_path is None


@pytest.mark.asyncio
async def test_finalize_trace_safe_when_no_tracer():
    """Calling finalize without init must not raise (e.g. early run failure)."""
    fake_storage = MagicMock()
    fake_storage.put_text = AsyncMock()
    services = _make_services(storage=fake_storage)
    router = _make_router(services=services)
    await router._finalize_trace("test-run-id")
    fake_storage.put_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_trace_swallows_s3_upload_errors():
    """S3 upload failure must not raise — the trace artifact is non-critical."""
    fake_storage = MagicMock()
    fake_storage.put_text = AsyncMock(side_effect=RuntimeError("s3 dead"))
    services = _make_services(storage=fake_storage)
    router = _make_router(services=services)
    router._init_trace("run")
    router._tracer.agent("a", "A")

    await router._finalize_trace("run")

    assert router._tracer is None
    assert router._trace_local_path is None


@pytest.mark.asyncio
async def test_finalize_trace_skips_when_storage_unavailable():
    """In CLI mode (services.storage is None) the finalize is a no-op upload."""
    services = _make_services(storage=None)
    # Override storage to None explicitly; need to bypass the default MagicMock
    services = Services(
        db=MagicMock(),
        storage=None,  # type: ignore[arg-type]
        kg=None,
        vectors=None,
        embeddings=None,
    )
    router = _make_router(services=services)
    router._init_trace("run")
    router._tracer.agent("a", "A")
    local_path = router._trace_local_path

    await router._finalize_trace("run")

    assert router._tracer is None
    assert router._trace_local_path is None
    # local file is cleaned up regardless
    assert local_path is not None and not local_path.exists()
