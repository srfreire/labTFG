"""Tests for ``decisionlab.eval.report`` (markdown + JSON renderers)."""

from __future__ import annotations

import json

from decisionlab.eval.assertions import AssertionOutcome
from decisionlab.eval.kgadmin import KGStats
from decisionlab.eval.models import PipelineRunResult
from decisionlab.eval.report import render_json, render_markdown, write_report
from decisionlab.eval.suite import SuiteResult, SuiteSpec, TopicResult
from decisionlab.router import Stage
from decisionlab.runtime.tool_calls import ToolCall


def _spec() -> SuiteSpec:
    return SuiteSpec(
        name="test-suite",
        stages=(Stage.RESEARCH,),
        reset_kg_before=False,
        env_spec_path=None,
        project_root=None,  # type: ignore[arg-type]
        reports_root=None,  # type: ignore[arg-type]
        topics=(),
        max_usd_total=None,
        source_path=None,
    )


def _topic_result() -> TopicResult:
    run = PipelineRunResult(
        run_id="r1",
        topic="alpha",
        stages_run=(Stage.RESEARCH,),
        paradigms=("rl", "prospect"),
        memory_per_stage={
            "researcher": {
                "nodes_created": 5,
                "relations_created": 2,
                "facts_stored": 3,
            }
        },
    )
    return TopicResult(
        topic="alpha",
        run=run,
        assertions={
            "research": [
                AssertionOutcome(name="paradigm", passed=True, detail="rl present"),
                AssertionOutcome(name="paradigm", passed=False, detail="ddm absent"),
            ]
        },
    )


def _suite_result(*, with_kg_growth: bool = True) -> SuiteResult:
    pre = KGStats(total_nodes=10, total_relations=4) if with_kg_growth else None
    post = KGStats(total_nodes=15, total_relations=6) if with_kg_growth else None
    return SuiteResult(
        suite=_spec(),
        topic_results=(_topic_result(),),
        pre_stats=pre,
        post_stats=post,
        total_usd=1.23,
        duration_ms=4321,
        budget_exhausted=False,
    )


class TestRenderMarkdown:
    def test_includes_headline_overall_status(self):
        md = render_markdown(_suite_result())
        assert "# Eval suite: `test-suite`" in md
        assert "**Overall**: FAIL" in md  # one assertion failed

    def test_kg_growth_section_when_stats_present(self):
        md = render_markdown(_suite_result(with_kg_growth=True))
        assert "## KG growth" in md
        assert "+5" in md  # nodes delta
        assert "+2" in md  # relations delta

    def test_kg_growth_omitted_without_stats(self):
        md = render_markdown(_suite_result(with_kg_growth=False))
        assert "## KG growth" not in md

    def test_assertion_table_rows(self):
        md = render_markdown(_suite_result())
        assert "| research | paradigm | ✓" in md
        assert "| research | paradigm | ✗" in md

    def test_budget_warning_when_exhausted(self):
        result = _suite_result()
        result = SuiteResult(
            suite=result.suite,
            topic_results=result.topic_results,
            pre_stats=result.pre_stats,
            post_stats=result.post_stats,
            total_usd=result.total_usd,
            duration_ms=result.duration_ms,
            budget_exhausted=True,
        )
        md = render_markdown(result)
        assert "Budget exhausted" in md


class TestRenderJson:
    def test_returns_parseable_json(self):
        s = render_json(_suite_result())
        data = json.loads(s)
        assert data["suite"]["name"] == "test-suite"
        assert data["topics"][0]["topic"] == "alpha"
        assert len(data["topics"][0]["assertions"]["research"]) == 2
        assert data["topics"][0]["assertions"]["research"][0]["passed"] is True

    def test_kg_section_serialised(self):
        s = render_json(_suite_result(with_kg_growth=True))
        data = json.loads(s)
        assert data["kg"]["before"]["total_nodes"] == 10
        assert data["kg"]["after"]["total_nodes"] == 15

    def test_kg_section_null_without_stats(self):
        s = render_json(_suite_result(with_kg_growth=False))
        data = json.loads(s)
        assert data["kg"]["before"] is None
        assert data["kg"]["after"] is None

    def test_tool_call_log_serialised_per_topic(self):
        tr = _topic_result()
        run = PipelineRunResult(
            run_id=tr.run.run_id,
            topic=tr.run.topic,
            stages_run=tr.run.stages_run,
            paradigms=tr.run.paradigms,
            memory_per_stage=tr.run.memory_per_stage,
            tool_call_log=(
                ToolCall(
                    name="retrieve_knowledge",
                    stage="research",
                    args_hash="abc",
                    succeeded=True,
                ),
                ToolCall(
                    name="web_search",
                    stage="research",
                    args_hash="def",
                    succeeded=False,
                ),
            ),
        )
        result = SuiteResult(
            suite=_spec(),
            topic_results=(TopicResult(topic="alpha", run=run, assertions={}),),
            pre_stats=None,
            post_stats=None,
            total_usd=0.0,
            duration_ms=0,
            budget_exhausted=False,
        )
        data = json.loads(render_json(result))
        log = data["topics"][0]["run"]["tool_call_log"]
        assert [c["name"] for c in log] == ["retrieve_knowledge", "web_search"]
        assert log[0]["succeeded"] is True
        assert log[1]["succeeded"] is False


class TestWriteReport:
    def test_writes_md_and_json_to_dir(self, tmp_path):
        out = tmp_path / "out"
        md_path, json_path = write_report(_suite_result(), out)
        assert md_path.exists() and md_path.name == "report.md"
        assert json_path.exists() and json_path.name == "report.json"
        assert md_path.read_text().startswith("# Eval suite")
        json.loads(json_path.read_text())  # roundtrips
