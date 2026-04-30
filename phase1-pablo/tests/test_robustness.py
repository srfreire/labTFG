"""P4-003: Robustness tests — absurd input to every agent, verify graceful handling.

Each test sends nonsensical / absurd input and mocks the LLM to simulate
detection of the invalid input.  We verify:
  1. No uncaught exceptions (the agent does not crash)
  2. Agents with validation (P4-001/P4-002) write "status": "invalid" reports
  3. Output clearly indicates something is wrong
"""

from __future__ import annotations

import json
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

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


class _StreamCM:
    """Async context manager wrapping a single ``Message``-shaped response."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_final_message(self):
        return self._response


def _mock_client(*responses) -> MagicMock:
    """Create a client mock that wires both ``messages.create`` and
    ``messages.stream`` against a shared queue. Whichever path the agent
    loop picks (based on max_tokens) consumes the next response.

    Researcher (32k) goes through stream; Formalizer/Reasoner/Builder (16k)
    and DeepResearcher (16k) go through create. The shared queue lets a
    single test cover Researcher → DeepResearcher chains where calls
    interleave between paths.
    """
    queue = list(responses)
    if len(queue) == 1:
        # Single response → return it on every call. Matches the pre-streaming
        # ``client.messages.create.return_value = X`` behaviour the
        # max-iterations robustness tests rely on.
        single = queue[0]

        def get_response(**_kw):
            return single

        def get_stream(**_kw):
            return _StreamCM(single)
    else:
        iterator = iter(queue)

        def get_response(**_kw):
            return next(iterator)

        def get_stream(**_kw):
            return _StreamCM(next(iterator))

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=get_response)
    client.messages.stream = MagicMock(side_effect=get_stream)
    return client


def _assert_invalid_report(
    s3_store: dict, prefix: str, subdir: str, filename: str, min_problems: int = 1
):
    """Assert a validation report exists in mock S3 with status 'invalid' and enough problems."""
    key = f"{prefix}/{subdir}/{filename}"
    assert key in s3_store, (
        f"Expected key {key} in S3 store, got: {list(s3_store.keys())}"
    )
    data = json.loads(s3_store[key])
    assert data["status"] == "invalid"
    assert len(data["problems"]) >= min_problems


def _make_s3_mock(s3_store: dict | None = None):
    """Return (s3_store, mock_storage_obj) for patching shared.storage."""
    if s3_store is None:
        s3_store = {}

    async def fake_get_text(key):
        if key not in s3_store:
            raise FileNotFoundError(key)
        return s3_store[key]

    async def fake_put_text(key, content):
        s3_store[key] = content

    async def fake_get(key):
        if key not in s3_store:
            raise FileNotFoundError(key)
        val = s3_store[key]
        return val.encode() if isinstance(val, str) else val

    async def fake_list(prefix):
        return [k for k in s3_store if k.startswith(prefix)]

    mock = MagicMock()
    mock.get_text = AsyncMock(side_effect=fake_get_text)
    mock.put_text = AsyncMock(side_effect=fake_put_text)
    mock.get = AsyncMock(side_effect=fake_get)
    mock.list = AsyncMock(side_effect=fake_list)

    return s3_store, mock


# ═══════════════════════════════════════════════════════════════════════════
# Researcher — absurd problem descriptions
# ═══════════════════════════════════════════════════════════════════════════


class TestResearcherRobustness:
    """Researcher receives nonsensical problem strings."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "absurd_input",
        [
            "asdfghjkl",
            "🎉🎉🎉",
            "",
            "x" * 10_000,
            "../../etc/passwd",
            "12345 67890 !@#$%",
        ],
    )
    async def test_does_not_crash_on_absurd_input(self, absurd_input):
        """Researcher.run() must return a ResearchReport without raising."""
        final = _response(
            "end_turn",
            [
                _text_block(
                    "I could not identify any valid decision-making paradigms from this input."
                )
            ],
        )
        client = _mock_client(final)

        r = Researcher(client=client, search=MockWebSearch())
        report = await r.run(absurd_input)

        assert isinstance(report, ResearchReport)

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_paradigms(self):
        """Empty problem -> LLM signals nothing found -> empty paradigms list."""
        final = _response(
            "end_turn",
            [
                _text_block(
                    "No paradigms could be identified from an empty problem description."
                )
            ],
        )
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
        final = _response(
            "end_turn",
            [_text_block("The search returned no relevant decision-making paradigms.")],
        )
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
        deep_text = _text_block(
            "# asdfghjkl — Deep research\n\nNo coherent literature found."
        )
        deep_loop_resp = _response("end_turn", [deep_text])
        # - summary extraction call
        deep_summary = MagicMock()
        deep_summary.content = [_text_block("No valid paradigm found.")]

        # Step 2: Researcher LLM ends
        final = _response(
            "end_turn",
            [
                _text_block(
                    "Deep research for 'asdfghjkl nonsense' found nothing useful."
                )
            ],
        )

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
    async def test_incoherent_report_no_crash(self):
        """Deep report is gibberish -> LLM reads it, signals failure, no crash."""
        _s3_store, mock_storage = _make_s3_mock(
            {
                "research/run-1/deep/gibberish.md": (
                    "asdfghjkl 🎉🎉🎉 qwertyuiop !@#$% lorem ipsum dolor sit amet "
                    "this is not a real research report and contains no paradigm info."
                ),
            }
        )

        read_call = _tool_block("c1", "read_file", {"path": "deep/gibberish.md"})
        resp1 = _response("tool_use", [read_call])

        write_call = _tool_block(
            "c2",
            "write_file",
            {
                "path": "formulations/gibberish.md",
                "content": "# Unable to formalize\n\nThe deep report contains no "
                "coherent paradigm information to produce formulations from.",
            },
        )
        resp2 = _response("tool_use", [write_call])

        final = _response(
            "end_turn",
            [
                _text_block(
                    "The deep report for 'gibberish' does not contain valid paradigm "
                    "information. No formulations could be produced."
                )
            ],
        )
        client = _mock_client(resp1, resp2, final)

        with patch("shared.storage", mock_storage):
            agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
            result = await agent.run("gibberish")

        assert isinstance(result, str)
        assert result

    @pytest.mark.asyncio
    async def test_missing_deep_report_no_crash(self):
        """Deep report file doesn't exist -> read_file returns error -> no crash."""
        _s3_store, mock_storage = _make_s3_mock()

        read_call = _tool_block("c1", "read_file", {"path": "deep/nonexistent.md"})
        resp1 = _response("tool_use", [read_call])
        final = _response(
            "end_turn",
            [_text_block("Could not read the deep report — file not found.")],
        )
        client = _mock_client(resp1, final)

        with patch("shared.storage", mock_storage):
            agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
            result = await agent.run("nonexistent")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_emoji_slug_no_crash(self):
        """Paradigm slug is pure emojis -> agent handles gracefully."""
        final = _response("end_turn", [_text_block("Invalid paradigm slug.")])
        client = _mock_client(final)

        agent = FormalizerSubAgent(client=client, research_prefix="research/run-1")
        result = await agent.run("🎉🎉🎉")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# ReasonerSubAgent — nonsensical formulations (P4-001 validation)
# ═══════════════════════════════════════════════════════════════════════════


class TestReasonerSubRobustness:
    """ReasonerSubAgent receives incoherent formulations and detects problems."""

    _ENV_SPEC: ClassVar[dict] = {
        "actions": ["up", "down", "left", "right", "stay", "eat"]
    }

    def _setup_s3_store(self, slug: str, deep_text: str, form_text: str) -> dict:
        """Create S3 mock store with deep report, formulations, env_spec."""
        return {
            f"research/run-1/deep/{slug}.md": deep_text,
            f"research/run-1/formulations/{slug}.md": form_text,
            "research/run-1/env_spec.json": json.dumps(self._ENV_SPEC),
        }

    def _read_three_files_responses(self, slug: str):
        """Return the 3 mock responses for reading deep, formulations, env_spec."""
        return [
            _response(
                "tool_use",
                [_tool_block("c1", "read_file", {"path": f"deep/{slug}.md"})],
            ),
            _response(
                "tool_use",
                [_tool_block("c2", "read_file", {"path": f"formulations/{slug}.md"})],
            ),
            _response(
                "tool_use", [_tool_block("c3", "read_file", {"path": "env_spec.json"})]
            ),
        ]

    def _write_invalid_response(self, report: dict, path: str):
        """Return a mock response for writing a validation report."""
        return _response(
            "tool_use",
            [
                _tool_block(
                    "c4",
                    "write_file",
                    {
                        "path": path,
                        "content": json.dumps(report, indent=2),
                    },
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_detects_nonsense_and_writes_invalid(self):
        """Nonsensical formulations -> LLM detects -> writes status:invalid."""
        s3_store = self._setup_s3_store(
            "nonsense",
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
                {
                    "type": "undefined_variable",
                    "detail": "Variable 'banana' used in equation but not defined",
                },
                {
                    "type": "invalid_reference",
                    "detail": "Decision logic uses 'feeling_good' — no such variable exists",
                },
                {
                    "type": "other",
                    "detail": "Equation 'X = X + banana * 🎉' is mathematically incoherent",
                },
            ],
        }

        reads = self._read_three_files_responses("nonsense")
        write = self._write_invalid_response(
            invalid_report, "reasoner/nonsense-F01.json"
        )
        final = _response(
            "end_turn",
            [
                _text_block(
                    "Validation failed for formulation nonsense-F01. "
                    "Multiple incoherences detected — see validation report."
                )
            ],
        )
        client = _mock_client(*reads, write, final)

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = ReasonerSubAgent(
                client=client,
                research_prefix="research/run-1",
                models_prefix="models/run-1",
            )
            result = await agent.run("nonsense", formulation_slugs=["nonsense-F01"])

        assert isinstance(result, str)
        _assert_invalid_report(
            s3_store, "models/run-1", "reasoner", "nonsense-F01.json", min_problems=1
        )

    @pytest.mark.asyncio
    async def test_empty_formulations_no_crash(self):
        """Empty formulation file -> LLM detects, reports invalid, no crash."""
        s3_store = self._setup_s3_store(
            "empty",
            deep_text="# Empty paradigm\n\n",
            form_text="",
        )

        invalid_report = {
            "formulation_id": "empty-F01",
            "paradigm": "empty",
            "status": "invalid",
            "problems": [
                {
                    "type": "other",
                    "detail": "Formulation file is empty — no variables, equations, or decision logic found",
                },
            ],
        }

        reads = self._read_three_files_responses("empty")
        write = self._write_invalid_response(invalid_report, "reasoner/empty-F01.json")
        final = _response(
            "end_turn",
            [_text_block("Formulation file was empty. Wrote invalid report.")],
        )
        client = _mock_client(*reads, write, final)

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = ReasonerSubAgent(
                client=client,
                research_prefix="research/run-1",
                models_prefix="models/run-1",
            )
            result = await agent.run("empty", formulation_slugs=["empty-F01"])

        assert isinstance(result, str)
        _assert_invalid_report(s3_store, "models/run-1", "reasoner", "empty-F01.json")

    @pytest.mark.asyncio
    async def test_path_injection_slug_no_crash(self):
        """Slug with path traversal chars -> agent handles gracefully."""
        read_deep = _tool_block("c1", "read_file", {"path": "deep/../../etc/passwd.md"})
        resp1 = _response("tool_use", [read_deep])
        final = _response(
            "end_turn", [_text_block("Could not process — invalid file paths.")]
        )
        client = _mock_client(resp1, final)

        _s3_store, mock_storage = _make_s3_mock()
        with patch("shared.storage", mock_storage):
            agent = ReasonerSubAgent(
                client=client,
                research_prefix="research/run-1",
                models_prefix="models/run-1",
            )
            result = await agent.run("../../etc/passwd")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# BuilderSubAgent — broken / absurd JSON spec (P4-002 validation)
# ═══════════════════════════════════════════════════════════════════════════


class TestBuilderSubRobustness:
    """BuilderSubAgent receives a broken or absurd JSON spec."""

    def _write_spec_to_s3(self, s3_store: dict, spec_id: str, spec_content):
        """Write a spec to mock S3 store; return relative path."""
        if isinstance(spec_content, str):
            content = spec_content
        else:
            content = json.dumps(spec_content, indent=2)
        s3_store[f"models/run-1/reasoner/{spec_id}.json"] = content
        return f"reasoner/{spec_id}.json"

    def _read_then_write_invalid(self, spec_path: str, validation: dict):
        """Return mock responses for: read spec -> write validation report -> final text."""
        read_call = _tool_block("c1", "read_file", {"path": spec_path})
        resp1 = _response("tool_use", [read_call])

        val_path = spec_path.replace("reasoner/", "builder/").replace(
            ".json", "_validation.json"
        )
        write_call = _tool_block(
            "c2",
            "write_file",
            {
                "path": val_path,
                "content": json.dumps(validation, indent=2),
            },
        )
        resp2 = _response("tool_use", [write_call])

        return resp1, resp2

    @pytest.mark.asyncio
    async def test_absurd_spec_writes_validation_report(self, tmp_path):
        """Spec with nonsensical decision_logic -> LLM writes validation report."""
        s3_store: dict[str, str] = {}
        spec_id = "nonsense-spec"
        spec_path = self._write_spec_to_s3(
            s3_store,
            spec_id,
            {
                "formulation_id": spec_id,
                "paradigm": "nonsense",
                "name": "Nonsense Model",
                "description": "asdfghjkl",
                "variables": [
                    {
                        "symbol": "🎉",
                        "name": "party",
                        "description": "???",
                        "type": "float",
                        "initial_value": 0,
                        "range": [0, 1],
                    },
                ],
                "parameters": [],
                "rules": [
                    {
                        "id": "R1",
                        "description": "???",
                        "type": "???",
                        "pseudocode": "🎉 = 🎉 + banana",
                        "source_postulate": "???",
                    },
                ],
                "decision_logic": {
                    "description": "do something",
                    "pseudocode": ["use judgment to decide wisely", "consider context"],
                },
                "env_mapping": {
                    "perception_to_variables": {
                        "temperature": "perception.temperature"
                    },
                    "actions_used": ["fly", "teleport"],
                    "reward_source": "magic",
                },
                "expected_behaviors": [
                    {
                        "id": "B1",
                        "description": "it works",
                        "test_pseudocode": "just trust me",
                    },
                ],
                "references": [],
            },
        )

        validation = {
            "formulation_id": spec_id,
            "paradigm": "nonsense",
            "status": "invalid",
            "problems": [
                {
                    "type": "ambiguous_logic",
                    "detail": "'use judgment to decide wisely' is not translatable to code",
                },
                {
                    "type": "missing_perception_key",
                    "detail": "perception_to_variables maps 'temperature' but perception has no such key",
                },
                {
                    "type": "untestable_behavior",
                    "detail": "B1 test_pseudocode 'just trust me' is not automatable",
                },
                {
                    "type": "other",
                    "detail": "actions_used includes 'fly' and 'teleport' which don't exist in the environment",
                },
            ],
        }
        resp1, resp2 = self._read_then_write_invalid(spec_path, validation)
        final = _response(
            "end_turn",
            [
                _text_block(
                    "Spec 'nonsense-spec' failed validation. Multiple issues detected."
                )
            ],
        )
        client = _mock_client(resp1, resp2, final)

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = BuilderSubAgent(
                client=client, models_prefix="models/run-1", project_root=tmp_path
            )
            result = await agent.run(spec_id, spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(
            s3_store,
            "models/run-1",
            "builder",
            f"{spec_id}_validation.json",
            min_problems=3,
        )
        # No model/test files should be created for invalid specs
        assert f"models/run-1/builder/{spec_id}_model.py" not in s3_store
        assert f"models/run-1/builder/test_{spec_id}.py" not in s3_store

    @pytest.mark.asyncio
    async def test_empty_spec_no_crash(self, tmp_path):
        """Empty/minimal spec -> LLM detects, writes validation report."""
        s3_store: dict[str, str] = {}
        spec_id = "empty-spec"
        spec_path = self._write_spec_to_s3(s3_store, spec_id, {})

        validation = {
            "formulation_id": spec_id,
            "paradigm": "unknown",
            "status": "invalid",
            "problems": [
                {
                    "type": "other",
                    "detail": "Spec is empty — no variables, rules, or decision logic found",
                },
            ],
        }
        resp1, resp2 = self._read_then_write_invalid(spec_path, validation)
        final = _response("end_turn", [_text_block("Empty spec — validation failed.")])
        client = _mock_client(resp1, resp2, final)

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = BuilderSubAgent(
                client=client, models_prefix="models/run-1", project_root=tmp_path
            )
            result = await agent.run(spec_id, spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(
            s3_store, "models/run-1", "builder", f"{spec_id}_validation.json"
        )
        assert f"models/run-1/builder/{spec_id}_model.py" not in s3_store

    @pytest.mark.asyncio
    async def test_malformed_json_spec_no_crash(self, tmp_path):
        """Spec file contains invalid JSON -> read succeeds (it's text), LLM handles it."""
        s3_store: dict[str, str] = {}
        spec_path = self._write_spec_to_s3(s3_store, "broken", "this is not json {{{")

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

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = BuilderSubAgent(
                client=client, models_prefix="models/run-1", project_root=tmp_path
            )
            result = await agent.run("broken", spec_path)

        assert isinstance(result, str)
        _assert_invalid_report(
            s3_store, "models/run-1", "builder", "broken_validation.json"
        )
        assert "models/run-1/builder/broken_model.py" not in s3_store

    @pytest.mark.asyncio
    async def test_spec_not_found_no_crash(self, tmp_path):
        """Spec file doesn't exist -> read_file returns error -> LLM ends gracefully."""
        s3_store: dict[str, str] = {}

        read_call = _tool_block("c1", "read_file", {"path": "reasoner/ghost.json"})
        resp1 = _response("tool_use", [read_call])
        final = _response(
            "end_turn", [_text_block("Could not read spec file — file not found.")]
        )
        client = _mock_client(resp1, final)

        _, mock_storage = _make_s3_mock(s3_store)
        with patch("shared.storage", mock_storage):
            agent = BuilderSubAgent(
                client=client, models_prefix="models/run-1", project_root=tmp_path
            )
            result = await agent.run("ghost", "reasoner/ghost.json")

        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════════
# Max-iterations safety — agents hit the loop limit without crashing
# ═══════════════════════════════════════════════════════════════════════════


class TestMaxIterationsRobustness:
    """Agents that receive absurd input may cause the LLM to loop endlessly.
    Verify RuntimeError is raised (expected behavior) rather than hanging."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_cls, run_args, read_path",
        [
            (FormalizerSubAgent, ("loop",), "deep/loop.md"),
            (ReasonerSubAgent, ("loop",), "deep/loop.md"),
            (BuilderSubAgent, ("loop", "reasoner/loop.json"), "reasoner/loop.json"),
        ],
        ids=["formalizer", "reasoner", "builder"],
    )
    async def test_max_iterations_raises(
        self, tmp_path, agent_cls, run_args, read_path
    ):
        """Agent stuck in tool loop -> RuntimeError, not a hang."""
        stuck_resp = _response(
            "tool_use",
            [
                _tool_block("c1", "read_file", {"path": read_path}),
            ],
        )
        client = _mock_client(stuck_resp)

        if agent_cls is FormalizerSubAgent:
            kwargs = {"client": client, "research_prefix": "research/run-1"}
        elif agent_cls is ReasonerSubAgent:
            kwargs = {
                "client": client,
                "research_prefix": "research/run-1",
                "models_prefix": "models/run-1",
            }
        elif agent_cls is BuilderSubAgent:
            kwargs = {
                "client": client,
                "models_prefix": "models/run-1",
                "project_root": tmp_path,
            }
        else:
            kwargs = {"client": client}

        _s3_store, mock_storage = _make_s3_mock()
        with patch("shared.storage", mock_storage):
            agent = agent_cls(**kwargs)
            with pytest.raises(RuntimeError, match="Max iterations"):
                await agent.run(*run_args)
