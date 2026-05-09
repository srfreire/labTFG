"""run_pipeline must populate result.timing with at least one stage."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.eval.runner import run_pipeline
from decisionlab.eval.timing import record_stage
from decisionlab.router import Stage
from shared.services import Services


def _services():
    return Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=None,
        vectors=None,
        embeddings=None,
    )


class _TimingRouter:
    """Router test double that exercises the ``record_stage`` collector."""

    def __init__(self, *, state, **_kw):
        self.state = state
        self.memory_results: dict[str, dict] = {}

    async def run(self):
        async with record_stage("researcher"):
            self.state.approved_paradigms = []
            self.state.selected_formulations = {}
            self.state.approved_specs = {}
        self.state.stage = Stage.DONE


@pytest.fixture
def patch_run_row():
    with patch(
        "decisionlab.eval.runner._create_run_row", new=AsyncMock(return_value=None)
    ):
        yield


@pytest.mark.asyncio
async def test_run_pipeline_populates_timing(tmp_path, patch_run_row):
    client = AsyncMock()
    search = AsyncMock()
    with patch("decisionlab.eval.runner.Router", _TimingRouter):
        result = await run_pipeline(
            "homeostasis under uncertainty",
            services=_services(),
            stages=[Stage.RESEARCH],
            project_root=tmp_path,
            client=client,
            search=search,
            reports_root=tmp_path / "reports",
            run_id="22222222-2222-4222-8222-222222222222",
        )
    assert result.timing is not None
    assert len(result.timing.stages) >= 1
    assert any(s.stage == "researcher" for s in result.timing.stages)
