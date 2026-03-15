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
