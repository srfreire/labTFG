"""P4-003: Robustness tests — absurd input to every agent, verify graceful handling.

Each test sends nonsensical / absurd input and mocks the LLM to simulate
detection of the invalid input.  We verify:
  1. No uncaught exceptions (the agent does not crash)
  2. Agents with validation (P4-001/P4-002) write "status": "invalid" reports
  3. Output clearly indicates something is wrong
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.adapters.mock import MockWebSearch
from decisionlab.agents.builder_sub import BuilderSubAgent
from decisionlab.agents.formalizer_sub import FormalizerSubAgent
from decisionlab.agents.reasoner_sub import ReasonerSubAgent
from decisionlab.agents.researcher import Researcher
from decisionlab.domain.models import ResearchReport


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _tool_block(id: str, name: str, input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input
    return block


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _response(stop_reason: str, content: list) -> MagicMock:
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.content = content
    return resp


def _mock_client(*responses) -> AsyncMock:
    """Create an AsyncMock client with the given LLM responses.

    Single response: sets return_value.  Multiple: sets side_effect.
    """
    client = AsyncMock()
    if len(responses) == 1:
        client.messages.create.return_value = responses[0]
    else:
        client.messages.create.side_effect = list(responses)
    return client


def _assert_invalid_report(tmp_path, subdir: str, filename: str, min_problems: int = 1):
    """Assert a validation report exists with status 'invalid' and enough problems."""
    report_path = tmp_path / subdir / filename
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["status"] == "invalid"
    assert len(data["problems"]) >= min_problems


# ═══════════════════════════════════════════════════════════════════════════
# Researcher — absurd problem descriptions
# ═══════════════════════════════════════════════════════════════════════════


class TestResearcherRobustness:
    """Researcher receives nonsensical problem strings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("absurd_input", [
        "asdfghjkl",
        "🎉🎉🎉",
        "",
        "x" * 10_000,
        "../../etc/passwd",
        "12345 67890 !@#$%",
    ])
    async def test_does_not_crash_on_absurd_input(self, absurd_input):
        """Researcher.run() must return a ResearchReport without raising."""
        final = _response("end_turn", [_text_block(
            "I could not identify any valid decision-making paradigms from this input."
        )])
        client = _mock_client(final)

        r = Researcher(client=client, search=MockWebSearch())
        report = await r.run(absurd_input)

        assert isinstance(report, ResearchReport)

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_paradigms(self):
        """Empty problem -> LLM signals nothing found -> empty paradigms list."""
        final = _response("end_turn", [_text_block(
            "No paradigms could be identified from an empty problem description."
        )])
        client = _mock_client(final)

        r = Researcher(client=client, search=MockWebSearch())
        report = await r.run("")

        assert isinstance(report, ResearchReport)
        assert len(report.paradigms) == 0
        assert report.summary

    @pytest.mark.asyncio
    async def test_gibberish_web_search_then_gives_up(self):
        """LLM does a web search with gibberish, gets nothing useful, ends."""
        search_call = _tool_block("c1", "web_search", {"query": "asdfghjkl"})
        resp1 = _response("tool_use", [search_call])
        final = _response("end_turn", [_text_block(
            "The search returned no relevant decision-making paradigms."
        )])
        client = _mock_client(resp1, final)

        r = Researcher(client=client, search=MockWebSearch(results=[]))
        report = await r.run("asdfghjkl")

        assert isinstance(report, ResearchReport)
        assert len(report.paradigms) == 0

    @pytest.mark.asyncio
    async def test_launch_deep_research_with_gibberish_no_crash(self):
        """LLM launches deep research on gibberish → sub-agent completes → no crash."""
        # Step 1: Researcher LLM calls launch_deep_research with gibberish
        launch_call = _tool_block(
            "c1", "launch_deep_research", {"paradigm": "asdfghjkl nonsense"}
        )
        resp1 = _response("tool_use", [launch_call])

        # DeepResearcher sub-agent runs its own loop:
        # - loop response (end_turn with some text)
        deep_text = _text_block("# asdfghjkl — Deep research\n\nNo coherent literature found.")
        deep_loop_resp = _response("end_turn", [deep_text])
        # - summary extraction call
        deep_summary = MagicMock()
        deep_summary.content = [_text_block("No valid paradigm found.")]

        # Step 2: Researcher LLM ends
        final = _response("end_turn", [_text_block(
            "Deep research for 'asdfghjkl nonsense' found nothing useful."
        )])

        client = _mock_client(resp1, deep_loop_resp, deep_summary, final)

        r = Researcher(client=client, search=MockWebSearch(results=[]))
        report = await r.run("asdfghjkl")

        assert isinstance(report, ResearchReport)
        assert "asdfghjkl nonsense" in report.deep_reports


# ═══════════════════════════════════════════════════════════════════════════
# FormalizerSubAgent — incoherent deep report
# ═══════════════════════════════════════════════════════════════════════════


class TestFormalizerSubRobustness:
    """FormalizerSubAgent receives a deep report full of nonsense."""

    @pytest.mark.asyncio
    async def test_incoherent_report_no_crash(self, tmp_path):
        """Deep report is gibberish -> LLM reads it, signals failure, no crash."""
        deep_dir = tmp_path / "deep"
        deep_dir.mkdir()
        (deep_dir / "gibberish.md").write_text(
            "asdfghjkl 🎉🎉🎉 qwertyuiop !@#$% lorem ipsum dolor sit amet "
            "this is not a real research report and contains no paradigm info."
        )

        read_call = _tool_block("c1", "read_file", {"path": "deep/gibberish.md"})
        resp1 = _response("tool_use", [read_call])

        write_call = _tool_block("c2", "write_file", {
            "path": "formulations/gibberish.md",
            "content": "# Unable to formalize\n\nThe deep report contains no "
                       "coherent paradigm information to produce formulations from.",
        })
        resp2 = _response("tool_use", [write_call])

        final = _response("end_turn", [_text_block(
            "The deep report for 'gibberish' does not contain valid paradigm "
            "information. No formulations could be produced."
        )])
        client = _mock_client(resp1, resp2, final)

        agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("gibberish")

        assert isinstance(result, str)
        assert result

    @pytest.mark.asyncio
    async def test_missing_deep_report_no_crash(self, tmp_path):
        """Deep report file doesn't exist -> read_file returns error -> no crash."""
        read_call = _tool_block("c1", "read_file", {"path": "deep/nonexistent.md"})
        resp1 = _response("tool_use", [read_call])
        final = _response("end_turn", [_text_block(
            "Could not read the deep report — file not found."
        )])
        client = _mock_client(resp1, final)

        agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("nonexistent")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_emoji_slug_no_crash(self, tmp_path):
        """Paradigm slug is pure emojis -> agent handles gracefully."""
        final = _response("end_turn", [_text_block("Invalid paradigm slug.")])
        client = _mock_client(final)

        agent = FormalizerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("🎉🎉🎉")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# ReasonerSubAgent — nonsensical formulations (P4-001 validation)
# ═══════════════════════════════════════════════════════════════════════════


class TestReasonerSubRobustness:
    """ReasonerSubAgent receives incoherent formulations and detects problems."""

    _ENV_SPEC = {"actions": ["up", "down", "left", "right", "stay", "eat"]}

    def _setup_reasoner_dirs(self, tmp_path, slug: str, deep_text: str, form_text: str):
        """Create deep report, formulations, env_spec, and reasoner output dir."""
        (tmp_path / "deep").mkdir(parents=True, exist_ok=True)
        (tmp_path / "deep" / f"{slug}.md").write_text(deep_text)

        (tmp_path / "formulations").mkdir(parents=True, exist_ok=True)
        (tmp_path / "formulations" / f"{slug}.md").write_text(form_text)

        (tmp_path / "env_spec.json").write_text(json.dumps(self._ENV_SPEC))
        (tmp_path / "reasoner").mkdir(parents=True, exist_ok=True)

    def _read_three_files_responses(self, slug: str):
        """Return the 3 mock responses for reading deep, formulations, env_spec."""
        return [
            _response("tool_use", [_tool_block("c1", "read_file", {"path": f"deep/{slug}.md"})]),
            _response("tool_use", [_tool_block("c2", "read_file", {"path": f"formulations/{slug}.md"})]),
            _response("tool_use", [_tool_block("c3", "read_file", {"path": "env_spec.json"})]),
        ]

    def _write_invalid_response(self, report: dict, path: str):
        """Return a mock response for writing a validation report."""
        return _response("tool_use", [_tool_block("c4", "write_file", {
            "path": path,
            "content": json.dumps(report, indent=2),
        })])

    @pytest.mark.asyncio
    async def test_detects_nonsense_and_writes_invalid(self, tmp_path):
        """Nonsensical formulations -> LLM detects -> writes status:invalid."""
        self._setup_reasoner_dirs(
            tmp_path, "nonsense",
            deep_text="# Nonsense paradigm\n\nasdfghjkl qwertyuiop the cat sat on the mat.",
            form_text=(
                "# Nonsense formulations\n\n## Formulation 1: Random\n"
                "### Variables\n| Symbol | Name |\n|--------|------|\n"
                "| X | unknown |\n\n### Equations\n"
                "X = X + banana * 🎉\n\n### Decision logic\n"
                "if feeling_good: do the thing\nelse: don't\n"
            ),
        )

        invalid_report = {
            "formulation_id": "nonsense-F01",
            "paradigm": "nonsense",
            "status": "invalid",
            "problems": [
                {"type": "undefined_variable", "detail": "Variable 'banana' used in equation but not defined"},
                {"type": "invalid_reference", "detail": "Decision logic uses 'feeling_good' — no such variable exists"},
                {"type": "other", "detail": "Equation 'X = X + banana * 🎉' is mathematically incoherent"},
            ],
        }

        reads = self._read_three_files_responses("nonsense")
        write = self._write_invalid_response(invalid_report, "reasoner/nonsense-F01.json")
        final = _response("end_turn", [_text_block(
            "Validation failed for formulation nonsense-F01. "
            "Multiple incoherences detected — see validation report."
        )])
        client = _mock_client(*reads, write, final)

        agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("nonsense", formulation_ids=["nonsense-F01"])

        assert isinstance(result, str)
        _assert_invalid_report(tmp_path, "reasoner", "nonsense-F01.json", min_problems=1)

    @pytest.mark.asyncio
    async def test_empty_formulations_no_crash(self, tmp_path):
        """Empty formulation file -> LLM detects, reports invalid, no crash."""
        self._setup_reasoner_dirs(
            tmp_path, "empty",
            deep_text="# Empty paradigm\n\n",
            form_text="",
        )

        invalid_report = {
            "formulation_id": "empty-F01",
            "paradigm": "empty",
            "status": "invalid",
            "problems": [
                {"type": "other", "detail": "Formulation file is empty — no variables, equations, or decision logic found"},
            ],
        }

        reads = self._read_three_files_responses("empty")
        write = self._write_invalid_response(invalid_report, "reasoner/empty-F01.json")
        final = _response("end_turn", [_text_block(
            "Formulation file was empty. Wrote invalid report."
        )])
        client = _mock_client(*reads, write, final)

        agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("empty", formulation_ids=["empty-F01"])

        assert isinstance(result, str)
        _assert_invalid_report(tmp_path, "reasoner", "empty-F01.json")

    @pytest.mark.asyncio
    async def test_path_injection_slug_no_crash(self, tmp_path):
        """Slug with path traversal chars -> agent handles gracefully."""
        read_deep = _tool_block("c1", "read_file", {"path": "deep/../../etc/passwd.md"})
        resp1 = _response("tool_use", [read_deep])
        final = _response("end_turn", [_text_block(
            "Could not process — invalid file paths."
        )])
        client = _mock_client(resp1, final)

        agent = ReasonerSubAgent(client=client, reports_dir=tmp_path)
        result = await agent.run("../../etc/passwd")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# BuilderSubAgent — broken / absurd JSON spec (P4-002 validation)
# ═══════════════════════════════════════════════════════════════════════════


class TestBuilderSubRobustness:
    """BuilderSubAgent receives a broken or absurd JSON spec."""

    def _write_spec(self, tmp_path, spec_id: str, spec_content):
        """Write a spec file to the reasoner dir; return relative path."""
        (tmp_path / "reasoner").mkdir(parents=True, exist_ok=True)
        (tmp_path / "builder").mkdir(parents=True, exist_ok=True)
        spec_path = tmp_path / "reasoner" / f"{spec_id}.json"
        if isinstance(spec_content, str):
            spec_path.write_text(spec_content)
        else:
            spec_path.write_text(json.dumps(spec_content, indent=2))
        return f"reasoner/{spec_id}.json"

    def _read_then_write_invalid(self, spec_path: str, validation: dict):
        """Return mock responses for: read spec -> write validation report -> final text."""
        read_call = _tool_block("c1", "read_file", {"path": spec_path})
        resp1 = _response("tool_use", [read_call])

        val_path = spec_path.replace("reasoner/", "builder/").replace(".json", "_validation.json")
        write_call = _tool_block("c2", "write_file", {
            "path": val_path,
            "content": json.dumps(validation, indent=2),
        })
        resp2 = _response("tool_use", [write_call])

        return resp1, resp2

    @pytest.mark.asyncio
    async def test_absurd_spec_writes_validation_report(self, tmp_path):
        """Spec with nonsensical decision_logic -> LLM writes validation report."""
        spec_id = "nonsense-spec"
        spec_path = self._write_spec(tmp_path, spec_id, {
            "formulation_id": spec_id,
            "paradigm": "nonsense",
            "name": "Nonsense Model",
            "description": "asdfghjkl",
            "variables": [
                {"symbol": "🎉", "name": "party", "description": "???", "type": "float", "initial_value": 0, "range": [0, 1]},
            ],
            "parameters": [],
            "rules": [
                {"id": "R1", "description": "???", "type": "???", "pseudocode": "🎉 = 🎉 + banana", "source_postulate": "???"},
            ],
            "decision_logic": {
                "description": "do something",
                "pseudocode": ["use judgment to decide wisely", "consider context"],
            },
            "env_mapping": {
                "perception_to_variables": {"temperature": "perception.temperature"},
                "actions_used": ["fly", "teleport"],
                "reward_source": "magic",
            },
            "expected_behaviors": [
                {"id": "B1", "description": "it works", "test_pseudocode": "just trust me"},
            ],
            "references": [],
        })

        validation = {
            "formulation_id": spec_id,
            "paradigm": "nonsense",
            "status": "invalid",
            "problems": [
                {"type": "ambiguous_logic", "detail": "'use judgment to decide wisely' is not translatable to code"},
                {"type": "missing_perception_key", "detail": "perception_to_variables maps 'temperature' but perception has no such key"},
                {"type": "untestable_behavior", "detail": "B1 test_pseudocode 'just trust me' is not automatable"},
                {"type": "other", "detail": "actions_used includes 'fly' and 'teleport' which don't exist in the environment"},
            ],
        }
        resp1, resp2 = self._read_then_write_invalid(spec_path, validation)
        final = _response("end_turn", [_text_block(
            "Spec 'nonsense-spec' failed validation. Multiple issues detected."
        )])
        client = _mock_client(resp1, resp2, final)

        agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
        result = await agent.run(spec_id, spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(tmp_path, "builder", f"{spec_id}_validation.json", min_problems=3)
        # No model/test files should be created for invalid specs
        assert not (tmp_path / "builder" / f"{spec_id}_model.py").exists()
        assert not (tmp_path / "builder" / f"test_{spec_id}.py").exists()

    @pytest.mark.asyncio
    async def test_empty_spec_no_crash(self, tmp_path):
        """Empty/minimal spec -> LLM detects, writes validation report."""
        spec_id = "empty-spec"
        spec_path = self._write_spec(tmp_path, spec_id, {})

        validation = {
            "formulation_id": spec_id,
            "paradigm": "unknown",
            "status": "invalid",
            "problems": [
                {"type": "other", "detail": "Spec is empty — no variables, rules, or decision logic found"},
            ],
        }
        resp1, resp2 = self._read_then_write_invalid(spec_path, validation)
        final = _response("end_turn", [_text_block("Empty spec — validation failed.")])
        client = _mock_client(resp1, resp2, final)

        agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
        result = await agent.run(spec_id, spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(tmp_path, "builder", f"{spec_id}_validation.json")
        assert not (tmp_path / "builder" / f"{spec_id}_model.py").exists()

    @pytest.mark.asyncio
    async def test_malformed_json_spec_no_crash(self, tmp_path):
        """Spec file contains invalid JSON -> read succeeds (it's text), LLM handles it."""
        spec_path = self._write_spec(tmp_path, "broken", "this is not json {{{")

        validation = {
            "formulation_id": "broken",
            "paradigm": "unknown",
            "status": "invalid",
            "problems": [
                {"type": "other", "detail": "Spec file does not contain valid JSON"},
            ],
        }
        resp1, resp2 = self._read_then_write_invalid(spec_path, validation)
        final = _response("end_turn", [_text_block("Invalid JSON — cannot build.")])
        client = _mock_client(resp1, resp2, final)

        agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
        result = await agent.run("broken", spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(tmp_path, "builder", "broken_validation.json")
        assert not (tmp_path / "builder" / "broken_model.py").exists()

    @pytest.mark.asyncio
    async def test_spec_not_found_no_crash(self, tmp_path):
        """Spec file doesn't exist -> read_file returns error -> LLM ends gracefully."""
        (tmp_path / "builder").mkdir(parents=True, exist_ok=True)

        read_call = _tool_block("c1", "read_file", {"path": "reasoner/ghost.json"})
        resp1 = _response("tool_use", [read_call])
        final = _response("end_turn", [_text_block(
            "Could not read spec file — file not found."
        )])
        client = _mock_client(resp1, final)

        agent = BuilderSubAgent(client=client, reports_dir=tmp_path, project_root=tmp_path)
        result = await agent.run("ghost", "reasoner/ghost.json")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# Max-iterations safety — agents hit the loop limit without crashing
# ═══════════════════════════════════════════════════════════════════════════


class TestMaxIterationsRobustness:
    """Agents that receive absurd input may cause the LLM to loop endlessly.
    Verify RuntimeError is raised (expected behavior) rather than hanging."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent_cls, run_args, read_path", [
        (FormalizerSubAgent, ("loop",), "deep/loop.md"),
        (ReasonerSubAgent, ("loop",), "deep/loop.md"),
        (BuilderSubAgent, ("loop", "reasoner/loop.json"), "reasoner/loop.json"),
    ], ids=["formalizer", "reasoner", "builder"])
    async def test_max_iterations_raises(self, tmp_path, agent_cls, run_args, read_path):
        """Agent stuck in tool loop -> RuntimeError, not a hang."""
        stuck_resp = _response("tool_use", [
            _tool_block("c1", "read_file", {"path": read_path}),
        ])
        client = _mock_client(stuck_resp)

        kwargs = {"client": client, "reports_dir": tmp_path}
        if agent_cls is BuilderSubAgent:
            kwargs["project_root"] = tmp_path
        agent = agent_cls(**kwargs)

        with pytest.raises(RuntimeError, match="Max iterations"):
            await agent.run(*run_args)
