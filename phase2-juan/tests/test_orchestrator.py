"""Integration tests for the Orchestrator agent (requires ANTHROPIC_API_KEY)."""
import asyncio
import os
from pathlib import Path

import anthropic
import pytest

from simlab.orchestrator import Orchestrator

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"


@pytest.mark.integration
def test_orchestrator_full_pipeline():
    output_dir = Path(__file__).resolve().parent.parent / "test_output"

    client = anthropic.AsyncAnthropic()
    orch = Orchestrator(
        client=client,
        research_dir=RESEARCH_DIR,
        output_dir=output_dir,
    )
    result = asyncio.run(orch.chat(
        "Crea un grid 6x6 con comida que se regenera, simula 2 agentes durante 15 pasos, "
        "observa que pasa, analiza los patrones y genera un informe PDF."
    ))

    # Should have completed the pipeline
    assert orch._state.get("spec") is not None
    assert orch._state.get("events") is not None
    assert orch._state.get("tracker_output") is not None
    assert orch._state.get("analyst_output") is not None

    # Clean up
    import shutil
    shutil.rmtree(output_dir, ignore_errors=True)


@pytest.mark.integration
def test_orchestrator_step_by_step():
    client = anthropic.AsyncAnthropic()
    orch = Orchestrator(
        client=client,
        research_dir=RESEARCH_DIR,
        output_dir=Path("/tmp/simlab_test"),
    )

    # Step 1: create environment
    result1 = asyncio.run(orch.chat("Crea un environment 5x5 con comida escasa."))
    assert orch._state.get("spec") is not None

    # Step 2: run simulation
    result2 = asyncio.run(orch.chat("Corre la simulacion con 2 agentes durante 10 pasos."))
    assert orch._state.get("events") is not None

    # Clean up
    import shutil
    shutil.rmtree(Path("/tmp/simlab_test"), ignore_errors=True)
