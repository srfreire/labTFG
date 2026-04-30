"""Tests for PipelineState and Stage enum."""

from decisionlab.router import PipelineState, Stage


class TestStageEnum:
    def test_stage_enum_values(self):
        expected = {
            "RESEARCH": "research",
            "MEMORY_RESEARCH": "memory_research",
            "REVIEW_RESEARCH": "review_research",
            "FORMALIZE": "formalize",
            "MEMORY_FORMALIZE": "memory_formalize",
            "REVIEW_FORMALIZE": "review_formalize",
            "GET_ENV_SPEC": "get_env_spec",
            "REASON": "reason",
            "MEMORY_REASON": "memory_reason",
            "REVIEW_REASON": "review_reason",
            "BUILD": "build",
            "MEMORY_BUILD": "memory_build",
            "REVIEW_BUILD": "review_build",
            "DONE": "done",
        }
        assert len(Stage) == 14
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
        assert state.approved_specs == {}
        assert state.build_results == {}
        assert state.pending_reruns == []

    def test_no_ids_field(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=tmp_path,
        )
        assert not hasattr(state, "ids")
        assert not hasattr(state, "topic_id")


class TestSelectedFormulationsUsesSlugs:
    def test_selected_formulations_accepts_slug_values(self, tmp_path):
        state = PipelineState(
            stage=Stage.REVIEW_FORMALIZE,
            problem="test",
            reports_dir=tmp_path,
            selected_formulations={
                "homeostatic-regulation": ["pi-controller", "dual-process"],
                "hedonic-reward": ["td-learning"],
            },
        )
        assert state.selected_formulations == {
            "homeostatic-regulation": ["pi-controller", "dual-process"],
            "hedonic-reward": ["td-learning"],
        }


class TestApprovedSpecsIsDict:
    def test_approved_specs_keyed_by_paradigm(self, tmp_path):
        state = PipelineState(
            stage=Stage.BUILD,
            problem="test",
            reports_dir=tmp_path,
            approved_specs={
                "homeostatic-regulation": ["pi-controller"],
                "hedonic-reward": ["td-learning"],
            },
        )
        assert state.approved_specs == {
            "homeostatic-regulation": ["pi-controller"],
            "hedonic-reward": ["td-learning"],
        }

    def test_approved_specs_default_empty_dict(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=tmp_path,
        )
        assert state.approved_specs == {}
        assert isinstance(state.approved_specs, dict)


class TestS3PrefixHelpers:
    def test_research_prefix(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=tmp_path,
            run_id="abc-123",
        )
        assert state.research_prefix == "research/abc-123"

    def test_models_prefix(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH,
            problem="test",
            reports_dir=tmp_path,
            run_id="abc-123",
        )
        assert state.models_prefix == "models/abc-123"
