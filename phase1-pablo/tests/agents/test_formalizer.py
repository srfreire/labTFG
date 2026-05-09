from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.agents.formalizer import Formalizer
from decisionlab.domain.models import FormalizationReport


def _make_storage(*, list_keys=None):
    storage = MagicMock()
    storage.list = AsyncMock(return_value=list_keys or [])
    return storage


def _make_db():
    return MagicMock()


def test_formalizer_construction():
    client = AsyncMock()
    f = Formalizer(
        client=client,
        research_prefix="research/run-1",
        storage=_make_storage(),
        db=_make_db(),
    )
    assert f.client is client
    assert f.research_prefix == "research/run-1"


@pytest.mark.asyncio
async def test_formalizer_run_collects_results():
    client = AsyncMock()
    f = Formalizer(
        client=client,
        research_prefix="research/run-1",
        storage=_make_storage(),
        db=_make_db(),
    )

    async def fake_run(slug):
        return f"# {slug} formulation"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run(["alpha", "beta"])

    assert isinstance(report, FormalizationReport)
    assert "alpha" in report.formulations
    assert "beta" in report.formulations
    assert report.formulations["alpha"] == "# alpha formulation"
    assert report.formulations["beta"] == "# beta formulation"


@pytest.mark.asyncio
async def test_formalizer_run_discovers_paradigms_from_s3():
    client = AsyncMock()
    storage = _make_storage(
        list_keys=[
            "research/run-1/deep/paradigm-a.md",
            "research/run-1/deep/paradigm-b.md",
        ]
    )
    f = Formalizer(
        client=client,
        research_prefix="research/run-1",
        storage=storage,
        db=_make_db(),
    )

    async def fake_run(slug):
        return f"# {slug} content"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run([])

    assert set(report.formulations.keys()) == {"paradigm-a", "paradigm-b"}


@pytest.mark.asyncio
async def test_formalizer_run_handles_partial_failure():
    client = AsyncMock()
    f = Formalizer(
        client=client,
        research_prefix="research/run-1",
        storage=_make_storage(),
        db=_make_db(),
    )

    call_count = 0

    async def fake_run(slug):
        nonlocal call_count
        call_count += 1
        if slug == "fail-me":
            raise RuntimeError("LLM exploded")
        return f"# {slug} ok"

    with patch("decisionlab.agents.formalizer.FormalizerSubAgent") as MockSub:
        instance = AsyncMock()
        instance.run.side_effect = fake_run
        MockSub.return_value = instance

        report = await f.run(["good", "fail-me"])

    assert "good" in report.formulations
    assert report.formulations["good"] == "# good ok"
    assert "fail-me" not in report.formulations
