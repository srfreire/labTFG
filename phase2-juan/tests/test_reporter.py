"""Integration tests for the Reporter agent (requires ANTHROPIC_API_KEY + tectonic)."""
import asyncio
import json
import os
import shutil
from pathlib import Path

import anthropic
import pytest

from simlab.reporter import Reporter

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)

RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"

TRACKER_OUTPUT = json.dumps({
    "summary": "Simulacion de 40 pasos con 2 agentes compitiendo por comida escasa en grid 10x10.",
    "trajectories": {
        "agresivo": {"steps_survived": 40, "resources_consumed": 5, "actions": {"move_right": 14, "move_left": 9, "move_up": 3, "move_down": 4, "eat": 5, "rest": 5}},
        "perezoso": {"steps_survived": 40, "resources_consumed": 1, "actions": {"rest": 22, "move_left": 8, "move_up": 6, "eat": 1, "move_down": 3}},
    },
    "episodes": [
        {"agent": "agresivo", "type": "foraging_success", "step": 5, "description": "Primera comida encontrada en step 5"},
        {"agent": "perezoso", "type": "starvation", "steps": [20, 35], "description": "Hambre critica: hunger subio de 15 a 30"},
        {"agent": "agresivo", "type": "exploitation", "steps": [10, 25], "description": "Se mantuvo cerca de fuentes de comida conocidas"},
    ],
})

ANALYST_OUTPUT = json.dumps({
    "patterns": [
        {"id": "P1", "type": "behavioral", "agents": ["agresivo"], "description": "Foraging regular cada 8 pasos", "evidence": "Consumos en steps 5, 13, 21, 29, 37"},
        {"id": "P2", "type": "strategic", "agents": ["perezoso"], "description": "Estrategia pasiva: descansa hasta hambre critica", "evidence": "22 acciones de descanso vs 1 comida"},
    ],
    "comparisons": [
        {"agents": ["agresivo", "perezoso"], "metric": "foraging_efficiency", "values": {"agresivo": 0.125, "perezoso": 0.025}, "insight": "Agresivo 5x mas eficiente"},
    ],
    "metrics": {
        "agresivo": {"survival_rate": 1.0, "avg_hunger": 4.0, "resources_per_step": 0.125},
        "perezoso": {"survival_rate": 1.0, "avg_hunger": 18.0, "resources_per_step": 0.025},
    },
})


@pytest.mark.integration
def test_reporter_generates_pdf():
    if not shutil.which("tectonic"):
        pytest.skip("tectonic not installed")

    output_dir = Path(__file__).resolve().parent.parent / "test_output"

    client = anthropic.AsyncAnthropic()
    reporter = Reporter(client=client)
    result = asyncio.run(reporter.run(
        "Genera un informe completo de la simulacion de competicion por comida.",
        TRACKER_OUTPUT,
        ANALYST_OUTPUT,
        research_dir=RESEARCH_DIR,
        output_dir=output_dir,
    ))

    # Reporter should return the PDF path or a message containing it
    pdf_path = output_dir / "report.pdf"
    assert pdf_path.exists(), f"PDF not generated. Reporter returned: {result[:200]}"

    # Cleanup
    shutil.rmtree(output_dir, ignore_errors=True)
