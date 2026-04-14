"""Tests for PipelineState, Stage enum, and IdRegistry."""

from pathlib import Path

import pytest

from decisionlab.domain.models import RerunRequest
from decisionlab.id_registry import IdRegistry
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
        assert isinstance(state.ids, IdRegistry)
        assert state.ids._paradigms == {}
        assert state.ids._formulations == {}


# ---------------------------------------------------------------------------
# IdRegistry unit tests
# ---------------------------------------------------------------------------


class TestIdRegistryAddParadigm:
    def test_first_paradigm(self):
        reg = IdRegistry()
        pid = reg.add_paradigm("homeostatic-regulation")
        assert pid == "T01-P01"

    def test_sequential_paradigms(self):
        reg = IdRegistry()
        p1 = reg.add_paradigm("homeostatic-regulation")
        p2 = reg.add_paradigm("hedonic-reward")
        assert p1 == "T01-P01"
        assert p2 == "T01-P02"

    def test_idempotent(self):
        reg = IdRegistry()
        p1 = reg.add_paradigm("homeostatic-regulation")
        p2 = reg.add_paradigm("homeostatic-regulation")
        assert p1 == p2 == "T01-P01"
        assert len(reg._paradigms) == 1

    def test_custom_topic_id(self):
        reg = IdRegistry(topic_id="T05")
        assert reg.add_paradigm("test") == "T05-P01"


class TestIdRegistryAddFormulation:
    def test_first_formulation(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        fid = reg.add_formulation("homeostatic-regulation", "pi-controller")
        assert fid == "T01-P01-F01"

    def test_sequential_formulations(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        f1 = reg.add_formulation("homeostatic-regulation", "pi-controller")
        f2 = reg.add_formulation("homeostatic-regulation", "dual-process")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P01-F02"

    def test_across_paradigms(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        reg.add_paradigm("hedonic-reward")
        f1 = reg.add_formulation("homeostatic-regulation", "pi-controller")
        f2 = reg.add_formulation("hedonic-reward", "temporal-difference")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P02-F01"

    def test_unknown_paradigm_raises(self):
        reg = IdRegistry()
        with pytest.raises(ValueError, match="not in registry"):
            reg.add_formulation("unknown-paradigm", "some-formulation")

    def test_idempotent(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        f1 = reg.add_formulation("homeostatic-regulation", "pi-controller")
        f2 = reg.add_formulation("homeostatic-regulation", "pi-controller")
        assert f1 == f2 == "T01-P01-F01"

    def test_same_name_different_paradigms(self):
        reg = IdRegistry()
        reg.add_paradigm("paradigm-a")
        reg.add_paradigm("paradigm-b")
        f1 = reg.add_formulation("paradigm-a", "baseline")
        f2 = reg.add_formulation("paradigm-b", "baseline")
        assert f1 == "T01-P01-F01"
        assert f2 == "T01-P02-F01"


class TestIdRegistryLookups:
    def test_paradigm_id(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        assert reg.paradigm_id("homeostatic-regulation") == "T01-P01"

    def test_paradigm_id_missing(self):
        reg = IdRegistry()
        assert reg.paradigm_id("nonexistent") is None

    def test_formulation_id(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        reg.add_formulation("homeostatic-regulation", "pi-controller")
        assert reg.formulation_id("homeostatic-regulation", "pi-controller") == "T01-P01-F01"

    def test_formulation_id_missing(self):
        reg = IdRegistry()
        assert reg.formulation_id("x", "y") is None

    def test_slug_for_id_paradigm(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        assert reg.slug_for_id("T01-P01") == "homeostatic-regulation"

    def test_slug_for_id_formulation(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        reg.add_formulation("homeostatic-regulation", "pi-controller")
        assert reg.slug_for_id("T01-P01-F01") == "homeostatic-regulation"

    def test_slug_for_id_missing(self):
        reg = IdRegistry()
        assert reg.slug_for_id("T01-P99") is None


class TestIdRegistryTree:
    def test_tree_structure(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")
        reg.add_paradigm("hedonic-reward")
        reg.add_formulation("homeostatic-regulation", "pi-controller")
        reg.add_formulation("homeostatic-regulation", "dual-process")
        reg.add_formulation("hedonic-reward", "td-learning")

        tree = reg.tree()
        assert list(tree.keys()) == ["homeostatic-regulation", "hedonic-reward"]
        assert tree["homeostatic-regulation"]["id"] == "T01-P01"
        assert tree["homeostatic-regulation"]["formulations"] == {
            "pi-controller": "T01-P01-F01",
            "dual-process": "T01-P01-F02",
        }
        assert tree["hedonic-reward"]["formulations"] == {
            "td-learning": "T01-P02-F01",
        }


class TestIdRegistrySerialization:
    def test_roundtrip(self):
        reg = IdRegistry(topic_id="T03")
        reg.add_paradigm("homeostatic-regulation")
        reg.add_paradigm("hedonic-reward")
        reg.add_formulation("homeostatic-regulation", "pi-controller")

        data = reg.to_dict()
        restored = IdRegistry.from_dict(data)

        assert restored.topic_id == "T03"
        assert restored.paradigm_id("homeostatic-regulation") == "T03-P01"
        assert restored.paradigm_id("hedonic-reward") == "T03-P02"
        assert restored.formulation_id("homeostatic-regulation", "pi-controller") == "T03-P01-F01"

    def test_continues_counters(self):
        reg = IdRegistry()
        reg.add_paradigm("homeostatic-regulation")

        restored = IdRegistry.from_dict(reg.to_dict())
        pid = restored.add_paradigm("hedonic-reward")
        assert pid == "T01-P02"

    def test_from_empty_dict(self):
        reg = IdRegistry.from_dict({})
        assert reg.topic_id == "T01"
        assert reg._paradigms == {}
        assert reg._formulations == {}


# ---------------------------------------------------------------------------
# PipelineState delegation tests
# ---------------------------------------------------------------------------


class TestPipelineStateDelegation:
    def test_assign_paradigm_id(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        pid = state.assign_paradigm_id("homeostatic-regulation")
        assert pid == "T01-P01"
        assert state.ids.paradigm_id("homeostatic-regulation") == "T01-P01"

    def test_assign_formulation_id(self, tmp_path):
        state = PipelineState(
            stage=Stage.FORMALIZE, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        fid = state.assign_formulation_id("homeostatic-regulation", "pi-controller")
        assert fid == "T01-P01-F01"

    def test_get_id(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        assert state.get_id("homeostatic-regulation") == "T01-P01"
        assert state.get_id("nonexistent") is None

    def test_get_slug(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
        )
        state.assign_paradigm_id("homeostatic-regulation")
        assert state.get_slug("T01-P01") == "homeostatic-regulation"
        assert state.get_slug("T01-P99") is None

    def test_topic_id_property(self, tmp_path):
        state = PipelineState(
            stage=Stage.RESEARCH, problem="test", reports_dir=tmp_path,
            ids=IdRegistry(topic_id="T05"),
        )
        assert state.topic_id == "T05"


class TestSelectedFormulationsUsesStringIds:
    def test_selected_formulations_accepts_string_ids(self, tmp_path):
        state = PipelineState(
            stage=Stage.REVIEW_FORMALIZE,
            problem="test",
            reports_dir=tmp_path,
            selected_formulations={"homeostatic": ["T01-P01-F01", "T01-P01-F03"]},
        )
        assert state.selected_formulations == {"homeostatic": ["T01-P01-F01", "T01-P01-F03"]}
