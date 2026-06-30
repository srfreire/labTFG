import json

from benchmark.lab_report import render_json, render_markdown, write_report

SAMPLE = {
    "case": "caso1",
    "seed": 42,
    "steps": 60,
    "env_spec": {
        "grid": {"width": 8, "height": 8},
        "actions": ["move_up", "eat", "stay"],
        "resources": [{"type": "food", "count": 6, "regenerate": True}],
    },
    "models": [
        {
            "key": "drift-diffusion-model/x",
            "short": "DDM (Wiener)",
            "events": 60,
            "total_reward": 7.0,
            "final_state_keys": ["v", "a"],
        },
        {
            "key": "homeostatic-regulation-of-food-valuation/y",
            "short": "Homeostasis",
            "events": 60,
            "total_reward": 5.0,
            "final_state_keys": ["energy_reserves"],
        },
    ],
    "joinable_triple": {
        "written": 6,
        "postgres_rows": 6,
        "qdrant_dense": 6,
        "qdrant_sparse": 6,
        "consistent": True,
        "episodes_filtered": 0,
    },
    "determinism": {"key": "drift-diffusion-model/x", "identical": True},
    "reporter": {
        "pdf_key": "experiments/e/report.pdf",
        "pdf_produced": True,
        "pdf_is_real_latex": True,
    },
    "latency_per_stage": {
        "architect": {"seconds": 3.0, "input_tokens": 10, "output_tokens": 5},
    },
    "usage": {
        "input_tokens": 100,
        "output_tokens": 20,
        "calls": 3,
        "seconds": 5.0,
        "estimated_cost_usd": 0.0123,
    },
    "total_seconds": 42.0,
}


def test_render_json_roundtrips():
    assert json.loads(render_json(SAMPLE)) == SAMPLE


def test_render_markdown_has_key_sections():
    md = render_markdown(SAMPLE)
    assert "caso1" in md
    assert "DDM (Wiener)" in md  # per-model table
    assert "Homeostasis" in md
    assert "consistent" in md.lower() or "joinable" in md.lower()
    assert "0.0123" in md  # estimated cost surfaced
    assert "determin" in md.lower()  # determinism section present


def test_write_report_creates_both_files(tmp_path):
    json_path, md_path = write_report(SAMPLE, tmp_path)
    assert json_path.name == "report.json"
    assert md_path.name == "report.md"
    assert json.loads(json_path.read_text()) == SAMPLE
    assert "caso1" in md_path.read_text()
