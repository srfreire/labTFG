"""Tests for assertion predicates and the registry dispatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from decisionlab.eval.assertions import (
    AssertionContext,
    predicate_names,
    register,
    run_assertion,
)
from decisionlab.eval.models import PipelineRunResult
from decisionlab.router import Stage
from shared.services import Services


def _result(
    *,
    paradigms=(),
    formulations=(),
    builder_artifacts=(),
    succeeded=True,
    started_at="2026-01-01T00:00:00+00:00",
    preexisting_paradigms=None,
) -> PipelineRunResult:
    return PipelineRunResult(
        run_id="r1",
        topic="t",
        stages_run=(Stage.RESEARCH,),
        paradigms=paradigms,
        formulations=formulations,
        builder_artifacts=builder_artifacts,
        failed_at=None if succeeded else Stage.RESEARCH,
        error=None if succeeded else "boom",
        started_at=started_at,
        preexisting_paradigms=preexisting_paradigms or {},
    )


def _ctx(**kw):
    services = Services(
        db=MagicMock(),
        storage=MagicMock(),
        kg=MagicMock(),
        vectors=None,
        embeddings=None,
    )
    return AssertionContext(result=_result(**kw), services=services)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestRunAssertion:
    @pytest.mark.asyncio
    async def test_unknown_predicate_returns_failed_outcome(self):
        out = await run_assertion({"definitely_not_a_predicate": 1}, _ctx())
        assert not out.passed
        assert "unknown predicate" in out.detail

    @pytest.mark.asyncio
    async def test_malformed_spec_returns_failed_outcome(self):
        out = await run_assertion({"a": 1, "b": 2}, _ctx())
        assert not out.passed
        assert "single-key" in out.detail

    @pytest.mark.asyncio
    async def test_predicate_exception_caught(self):
        @register("test_crashing")
        async def _crash(ctx, args):
            raise RuntimeError("kaboom")

        try:
            out = await run_assertion({"test_crashing": None}, _ctx())
            assert not out.passed
            assert "kaboom" in out.detail
        finally:
            from decisionlab.eval import assertions

            assertions._REGISTRY.pop("test_crashing", None)

    def test_predicate_names_returns_sorted(self):
        names = predicate_names()
        assert names == sorted(names)
        # Spot check known predicates exist.
        assert "paradigm" in names
        assert "min_nodes" in names
        assert "module_imports" in names


# ---------------------------------------------------------------------------
# Pipeline-result predicates
# ---------------------------------------------------------------------------


class TestParadigmPresent:
    @pytest.mark.asyncio
    async def test_pass_when_present(self):
        ctx = _ctx(paradigms=("rl", "prospect"))
        out = await run_assertion({"paradigm": "rl"}, ctx)
        assert out.passed

    @pytest.mark.asyncio
    async def test_fail_when_absent(self):
        ctx = _ctx(paradigms=("rl",))
        out = await run_assertion({"paradigm": "ddm"}, ctx)
        assert not out.passed
        assert "absent" in out.detail


class TestHasFormulation:
    @pytest.mark.asyncio
    async def test_pass_when_present(self):
        ctx = _ctx(formulations=("rl",))
        out = await run_assertion({"has_formulation": "rl"}, ctx)
        assert out.passed


class TestMinParadigms:
    @pytest.mark.asyncio
    async def test_pass_when_threshold_met(self):
        ctx = _ctx(paradigms=("a", "b", "c"))
        out = await run_assertion({"min_paradigms": 2}, ctx)
        assert out.passed

    @pytest.mark.asyncio
    async def test_fail_below_threshold(self):
        ctx = _ctx(paradigms=("a",))
        out = await run_assertion({"min_paradigms": 3}, ctx)
        assert not out.passed


class TestSucceeded:
    @pytest.mark.asyncio
    async def test_pass_on_success(self):
        out = await run_assertion({"succeeded": None}, _ctx(succeeded=True))
        assert out.passed

    @pytest.mark.asyncio
    async def test_fail_on_failure(self):
        out = await run_assertion({"succeeded": None}, _ctx(succeeded=False))
        assert not out.passed
        assert "failed" in out.detail


# ---------------------------------------------------------------------------
# KG predicates — patch kgadmin.query
# ---------------------------------------------------------------------------


class TestMinNodes:
    @pytest.mark.asyncio
    async def test_pass_when_count_meets_threshold(self):
        ctx = _ctx()
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[{"c": 5}]),
        ):
            out = await run_assertion({"min_nodes": {"label": "Paradigm", "n": 3}}, ctx)
        assert out.passed
        assert "5 nodes" in out.detail

    @pytest.mark.asyncio
    async def test_fail_when_below_threshold(self):
        ctx = _ctx()
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[{"c": 1}]),
        ):
            out = await run_assertion({"min_nodes": {"label": "Paradigm", "n": 3}}, ctx)
        assert not out.passed

    @pytest.mark.asyncio
    async def test_missing_label_arg_fails(self):
        out = await run_assertion({"min_nodes": {"n": 3}}, _ctx())
        assert not out.passed


class TestParadigmReused:
    @pytest.mark.asyncio
    async def test_pass_when_live_kg_created_before_run(self):
        ctx = _ctx(started_at="2026-01-02T00:00:00+00:00")
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[{"created_at": "2026-01-01T00:00:00+00:00"}]),
        ):
            out = await run_assertion({"paradigm_reused": "rl"}, ctx)
        assert out.passed
        assert "live KG" in out.detail

    @pytest.mark.asyncio
    async def test_pass_when_run_start_snapshot_has_paradigm(self):
        ctx = _ctx(
            started_at="2026-01-02T00:00:00+00:00",
            preexisting_paradigms={"rl": "2026-01-01T00:00:00+00:00"},
        )
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[]),
        ):
            out = await run_assertion({"paradigm_reused": "rl"}, ctx)
        assert out.passed
        assert "run-start KG snapshot" in out.detail

    @pytest.mark.asyncio
    async def test_fail_when_paradigm_created_after_run_start(self):
        ctx = _ctx(started_at="2026-01-01T00:00:00+00:00")
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[{"created_at": "2026-01-02T00:00:00+00:00"}]),
        ):
            out = await run_assertion({"paradigm_reused": "rl"}, ctx)
        assert not out.passed


class TestRelationExists:
    @pytest.mark.asyncio
    async def test_pass_when_count_positive(self):
        with patch(
            "decisionlab.eval.assertions.kg_query",
            new=AsyncMock(return_value=[{"c": 1}]),
        ):
            out = await run_assertion(
                {
                    "relation_exists": {
                        "from": "Paradigm",
                        "type": "BELONGS_TO",
                        "to": "Variable",
                    }
                },
                _ctx(),
            )
        assert out.passed

    @pytest.mark.asyncio
    async def test_missing_arg_fails(self):
        out = await run_assertion({"relation_exists": {"from": "X"}}, _ctx())
        assert not out.passed
        assert "missing" in out.detail


# ---------------------------------------------------------------------------
# Builder-output predicates
# ---------------------------------------------------------------------------

_BUILDER_MODULE = """
class FakeModel:
    def decide(self, perception):
        return {"kind": "MOVE", "direction": "north"}
    def update(self, *args, **kwargs):
        pass
    def get_state(self):
        return {}
"""

_CRASHING_MODULE = """
def boom():
    raise RuntimeError("module-level crash")
boom()
"""

_NO_DECIDE_MODULE = """
class NotADecisionModel:
    def something_else(self, p):
        return p
"""

_ACTION_OBJECT_MODULE = """
from dataclasses import dataclass

@dataclass
class Action:
    name: str
    params: dict

class FakeModel:
    def decide(self, perception):
        return Action(name="move_up", params={})
    def update(self, *args, **kwargs):
        pass
    def get_state(self):
        return {}
"""


class TestModuleImports:
    @pytest.mark.asyncio
    async def test_pass_when_module_imports(self, tmp_path):
        path = tmp_path / "rl-q-learning_model.py"
        path.write_text(_BUILDER_MODULE)
        ctx = _ctx(builder_artifacts=(path,))
        out = await run_assertion({"module_imports": "rl-q-learning"}, ctx)
        assert out.passed

    @pytest.mark.asyncio
    async def test_fail_when_no_artifact(self, tmp_path):
        ctx = _ctx(builder_artifacts=())
        out = await run_assertion({"module_imports": "rl-q-learning"}, ctx)
        assert not out.passed
        assert "no builder artifact" in out.detail

    @pytest.mark.asyncio
    async def test_fail_on_import_error(self, tmp_path):
        path = tmp_path / "broken_model.py"
        path.write_text(_CRASHING_MODULE)
        ctx = _ctx(builder_artifacts=(path,))
        out = await run_assertion({"module_imports": "broken"}, ctx)
        assert not out.passed
        assert "import failed" in out.detail


class TestDecideReturnsAction:
    @pytest.mark.asyncio
    async def test_pass_when_action_shaped(self, tmp_path):
        path = tmp_path / "rl_model.py"
        path.write_text(_BUILDER_MODULE)
        ctx = _ctx(builder_artifacts=(path,))
        out = await run_assertion(
            {
                "decide_returns_action": {
                    "spec_id": "rl",
                    "perception": {"x": 0, "y": 0},
                }
            },
            ctx,
        )
        assert out.passed

    @pytest.mark.asyncio
    async def test_pass_when_action_object(self, tmp_path):
        path = tmp_path / "rl_model.py"
        path.write_text(_ACTION_OBJECT_MODULE)
        ctx = _ctx(builder_artifacts=(path,))
        out = await run_assertion(
            {
                "decide_returns_action": {
                    "spec_id": "rl",
                    "perception": {"x": 0, "y": 0},
                }
            },
            ctx,
        )
        assert out.passed

    @pytest.mark.asyncio
    async def test_fail_when_no_decide_method(self, tmp_path):
        path = tmp_path / "nodec_model.py"
        path.write_text(_NO_DECIDE_MODULE)
        ctx = _ctx(builder_artifacts=(path,))
        out = await run_assertion({"decide_returns_action": {"spec_id": "nodec"}}, ctx)
        assert not out.passed
        assert "no class with a `decide` method" in out.detail

    @pytest.mark.asyncio
    async def test_missing_spec_id_fails(self, tmp_path):
        ctx = _ctx(builder_artifacts=(Path("/nope"),))
        out = await run_assertion({"decide_returns_action": {}}, ctx)
        assert not out.passed
