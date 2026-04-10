"""Tests for PipelineState and Stage enum."""

from pathlib import Path

import pytest

from decisionlab.domain.models import RerunRequest
from decisionlab.router import PipelineState, Stage


class TestStageEnum:
    def test_stage_enum_values(self):
        expected = {
            "RESEARCH": "research",
            "REVIEW_RESEARCH": "review_research",
            "FORMALIZE": "formalize",
            "REVIEW_FORMALIZE": "review_formalize",
            "GET_ENV_SPEC": "get_env_spec",
            "REASON": "reason",
            "REVIEW_REASON": "review_reason",
            "BUILD": "build",
            "REVIEW_BUILD": "review_build",
            "DONE": "done",
        }
        assert len(Stage) == 10
        for name, value in expected.items():
            assert Stage[name].value == value


class TestPipelineStateDefaults:
    def test_pipeline_state_defaults(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test problem",
            reports_dir=tmp_path,
        )
        assert state.approved_paradigms == []
        assert state.selected_formulations == {}
        assert state.env_spec_path is None
        assert state.approved_specs == []
        assert state.build_results == {}
        assert state.pending_reruns == []

    def test_id_registry_defaults(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        assert state.topic_id == "T01"
        assert state.id_registry == {}
        assert state._paradigm_counter == 0
        assert state._formulation_counters == {}


class TestSaveLoad:
    def test_save_load_roundtrip(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE,
            problem="decision under uncertainty",
            reports_dir=tmp_path,
            approved_paradigms=["homeostatic", "hedonic"],
        )
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert loaded.stage == Stage.FORMALIZE
        assert loaded.problem == "decision under uncertainty"
        assert loaded.reports_dir == tmp_path
        assert isinstance(loaded.reports_dir, Path)
        assert loaded.approved_paradigms == ["homeostatic", "hedonic"]

    def test_save_load_with_all_fields(self, tmp_path):
        env_path = tmp_path / "env_spec.json"
        env_path.write_text("{}")

        state = PipelineState(
            stage=Stage.REVIEW_BUILD,
            problem="full pipeline test",
            reports_dir=tmp_path,
            approved_paradigms=["homeostatic", "hedonic", "integrated"],
            selected_formulations={"homeostatic": [1, 3], "hedonic": [2]},
            env_spec_path=env_path,
            approved_specs=["spec_a", "spec_b"],
            build_results={"homeostatic": "ok", "hedonic": "fail"},
            pending_reruns=[
                RerunRequest(target="builder", paradigm="hedonic", feedback="test failure"),
            ],
        )
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert loaded.stage == Stage.REVIEW_BUILD
        assert loaded.problem == "full pipeline test"
        assert loaded.approved_paradigms == ["homeostatic", "hedonic", "integrated"]
        assert loaded.selected_formulations == {"homeostatic": [1, 3], "hedonic": [2]}
        assert loaded.env_spec_path == env_path
        assert loaded.approved_specs == ["spec_a", "spec_b"]
        assert loaded.build_results == {"homeostatic": "ok", "hedonic": "fail"}
        assert len(loaded.pending_reruns) == 1
        assert loaded.pending_reruns[0].target == "builder"
        assert loaded.pending_reruns[0].paradigm == "hedonic"
        assert loaded.pending_reruns[0].feedback == "test failure"

    def test_save_creates_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        assert not nested.exists()

        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=nested,
        )
        state.save()

        assert nested.exists()
        assert (nested / "pipeline_state.json").exists()

    def test_save_atomic_write(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=tmp_path,
        )
        state.save()

        tmp_files = list(tmp_path.glob(".state_*.tmp"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Pipeline state not found"):
            PipelineState.load(tmp_path)

    def test_load_corrupt_json(self, tmp_path):
        state_file = tmp_path / "pipeline_state.json"
        state_file.write_text("{{{not valid json!!!")

        with pytest.raises(ValueError, match="Corrupt pipeline state"):
            PipelineState.load(tmp_path)

    def test_load_reconstructs_paths(self, tmp_path):
        env_path = tmp_path / "env_spec.json"
        env_path.write_text("{}")

        state = PipelineState(
            stage=Stage.REASON,
            problem="test",
            reports_dir=tmp_path,
            env_spec_path=env_path,
        )
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert isinstance(loaded.reports_dir, Path)
        assert isinstance(loaded.env_spec_path, Path)

    def test_load_reconstructs_rerun_requests(self, tmp_path):
        state = PipelineState(
            stage=Stage.REVIEW_BUILD,
            problem="test",
            reports_dir=tmp_path,
            pending_reruns=[
                RerunRequest(target="reasoner", paradigm="homeostatic", feedback="bad spec"),
                RerunRequest(target="builder", paradigm="hedonic", feedback="import error"),
            ],
        )
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert len(loaded.pending_reruns) == 2
        for rr in loaded.pending_reruns:
            assert isinstance(rr, RerunRequest)
        assert loaded.pending_reruns[0].target == "reasoner"
        assert loaded.pending_reruns[1].paradigm == "hedonic"

    def test_save_load_with_build_results(self, tmp_path):
        results = {
            "homeostatic": "Module generated at models/homeostatic.py\nAll 5 tests passed.",
            "hedonic": "Module generated at models/hedonic.py\nError: 2 tests failed.",
        }
        state = PipelineState(
            stage=Stage.REVIEW_BUILD,
            problem="test",
            reports_dir=tmp_path,
            build_results=results,
        )
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert loaded.build_results == results


class TestAssignParadigmId:
    def test_first_paradigm(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        pid = state.assign_paradigm_id("homeostatic-regulation")
        assert pid == "T01-P01"
        assert state._paradigm_counter == 1
        assert state.id_registry["homeostatic-regulation"] == "T01-P01"

    def test_sequential_paradigms(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        p1 = state.assign_paradigm_id("homeostatic-regulation")
        p2 = state.assign_paradigm_id("hedonic-reward")
        assert p1 == "T01-P01"
        assert p2 == "T01-P02"
        assert state._paradigm_counter == 2

    def test_duplicate_slug_returns_existing(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        p1 = state.assign_paradigm_id("homeostatic-regulation")
        p2 = state.assign_paradigm_id("homeostatic-regulation")
        assert p1 == p2 == "T01-P01"
        assert state._paradigm_counter == 1


class TestAssignFormulationId:
    def test_first_formulation(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        fid = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        assert fid == "T01-P01-F01"
        assert state.id_registry["homeostatic-regulation::pi-controller"] == "T01-P01-F01"

    def test_sequential_formulations(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        f1 = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        f2 = state.assign_formulation_id("homeostatic-regulation", "dual-process")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P01-F02"

    def test_formulations_across_paradigms(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        state.assign_paradigm_id("hedonic-reward")
        f1 = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        f2 = state.assign_formulation_id("hedonic-reward", "temporal-difference")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P02-F01"

    def test_unknown_paradigm_raises(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        with pytest.raises(ValueError, match="not in registry"):
            state.assign_formulation_id("unknown-paradigm", "some-formulation")

    def test_duplicate_formulation_returns_existing(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        f1 = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        f2 = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        assert f1 == f2 == "T01-P01-F01"
        assert state._formulation_counters["T01-P01"] == 1

    def test_same_name_different_paradigms(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("paradigm-a")
        state.assign_paradigm_id("paradigm-b")
        f1 = state.assign_formulation_id("paradigm-a", "baseline")
        f2 = state.assign_formulation_id("paradigm-b", "baseline")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P02-F01"


class TestGetIdGetSlug:
    def test_get_id(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        assert state.get_id("homeostatic-regulation") == "T01-P01"

    def test_get_id_missing(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        assert state.get_id("nonexistent") is None

    def test_get_slug(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        assert state.get_slug("T01-P01") == "homeostatic-regulation"

    def test_get_slug_missing(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        assert state.get_slug("T01-P99") is None

    def test_get_slug_formulation(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        assert state.get_slug("T01-P01-F01") == "homeostatic-regulation::pi-controller"


class TestIdRegistryPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        state.assign_paradigm_id("hedonic-reward")
        state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        state.save()

        loaded = PipelineState.load(tmp_path)
        assert loaded.topic_id == "T01"
        assert loaded.id_registry == {
            "homeostatic-regulation": "T01-P01",
            "hedonic-reward": "T01-P02",
            "homeostatic-regulation::pi-controller": "T01-P01-F01",
        }
        assert loaded._paradigm_counter == 2
        assert loaded._formulation_counters == {"T01-P01": 1}

    def test_load_continues_counters(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        state.save()

        loaded = PipelineState.load(tmp_path)
        pid = loaded.assign_paradigm_id("hedonic-reward")
        assert pid == "T01-P02"

    def test_backward_compat_missing_registry(self, tmp_path):
        """Old pipeline_state.json without registry fields loads fine."""
        import json
        old_data = {
            "stage": "research",
            "problem": "test",
            "reports_dir": str(tmp_path),
        }
        (tmp_path / "pipeline_state.json").write_text(json.dumps(old_data))

        loaded = PipelineState.load(tmp_path)
        assert loaded.topic_id == "T01"
        assert loaded.id_registry == {}
        assert loaded._paradigm_counter == 0
        assert loaded._formulation_counters == {}
