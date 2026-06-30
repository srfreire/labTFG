import json

from benchmark.export_judge_bundle import export_judge_bundle


def test_export_bundle_structure(tmp_path):
    bundle = export_judge_bundle(
        tmp_path,
        env_spec={"grid": {"width": 8, "height": 8}},
        trajectories={
            "drift-diffusion-model/x": [
                {"step": 0, "action": "eat", "reward": 1.0, "state": {"v": 0.2}}
            ]
        },
        analyst_findings="## Hallazgos\nLos modelos difieren.",
        report_pdf=b"%PDF-1.5 fake",
        metrics={"case": "caso1", "seed": 42},
    )
    assert bundle.name == "judge-bundle"
    assert json.loads((bundle / "env_spec.json").read_text())["grid"]["width"] == 8
    traj = json.loads((bundle / "trajectories" / "drift-diffusion-model_x.json").read_text())
    assert traj[0]["action"] == "eat"
    assert (bundle / "analyst_findings.md").read_text().startswith("## Hallazgos")
    assert (bundle / "report.pdf").read_bytes() == b"%PDF-1.5 fake"
    assert json.loads((bundle / "metrics.json").read_text())["seed"] == 42


def test_export_bundle_omits_pdf_when_none(tmp_path):
    bundle = export_judge_bundle(
        tmp_path,
        env_spec={},
        trajectories={},
        analyst_findings="x",
        report_pdf=None,
        metrics={},
    )
    assert not (bundle / "report.pdf").exists()
    assert (bundle / "trajectories").is_dir()
