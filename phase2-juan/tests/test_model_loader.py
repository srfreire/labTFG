"""Tests for dynamic model discovery and loading."""
from pathlib import Path
from simlab.model_loader import discover_models, load_model

BUILDER_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run" / "builder"


def test_discover_finds_both_models():
    models = discover_models(BUILDER_DIR)
    assert len(models) >= 2
    assert "homeostatic-regulation_drive_reduction_rl" in models
    assert "homeostatic-regulation_pi_negative_feedback" in models


def test_model_info_has_required_fields():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_drive_reduction_rl"]
    assert info.formulation_id == "homeostatic-regulation_drive_reduction_rl"
    assert info.class_name == "HomeostaticDriveReductionRL"
    assert info.description  # non-empty docstring
    assert info.path.exists()
    assert info.model_class is not None


def test_load_model_returns_decision_model():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    model = load_model(info)
    assert hasattr(model, "decide")
    assert hasattr(model, "update")
    assert hasattr(model, "get_state")
    state = model.get_state()
    assert isinstance(state, dict)
    assert "energy" in state


def test_load_model_with_kwargs():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    model = load_model(info, energy_set_point=90.0)
    assert model.s == 90.0


def test_load_model_with_seed():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_drive_reduction_rl"]
    m1 = load_model(info, seed=42)
    m2 = load_model(info, seed=42)
    perception = {"x": 5, "y": 5, "grid_width": 10, "grid_height": 10, "step": 0,
                  "resources": {"food": [{"x": 6, "y": 5, "type": "food", "palatability": 0.8}]},
                  "last_action_result": {}}
    a1 = m1.decide(perception)
    a2 = m2.decide(perception)
    assert a1.name == a2.name


def test_load_model_bad_kwargs_raises():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    try:
        load_model(info, nonexistent_param=999)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_discover_skips_bad_files(tmp_path):
    bad_file = tmp_path / "broken_model.py"
    bad_file.write_text("raise SyntaxError('nope')")
    models = discover_models(tmp_path)
    assert len(models) == 0
