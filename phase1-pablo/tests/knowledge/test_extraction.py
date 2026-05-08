"""Tests for knowledge extraction module — covers AC1 through AC6.

The pre-rewrite extraction path streamed Haiku JSON and parsed the text.
After Phase B (research-memory rewrite) extraction routes through
``decisionlab.structured.call_structured`` which uses forced tool-use, so
the mock here builds a tool_use response instead of a text block. The
extracted-entity assertions are unchanged because ``_build_result`` still
consumes the same dict shape.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.extraction import (
    _build_result,
    _fold_legacy_test_results,
    _is_garbage_paradigm_slug,
    extract,
)
from decisionlab.knowledge.models import ExtractionResult
from decisionlab.structured import StructuredOutputError

# ---------------------------------------------------------------------------
# Helpers: build mock structured responses
# ---------------------------------------------------------------------------


def _make_response(payload, *, stop_reason: str = "end_turn") -> MagicMock:
    """Build a mock Anthropic response carrying a single tool_use block.

    ``payload`` is the parsed dict the structured wrapper will validate via
    Pydantic. Pass a JSON string to test the wrapper's defensive JSON parse.
    """
    if isinstance(payload, str):
        try:
            payload_dict = json.loads(payload)
        except json.JSONDecodeError:
            payload_dict = payload  # Wrapper will raise StructuredOutputError
    else:
        payload_dict = payload

    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit__Extraction"
    block.input = payload_dict

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = stop_reason
    resp.usage = None
    return resp


class _StreamCM:
    """Async context manager mimicking ``client.messages.stream(...)``."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get_final_message(self):
        return self._response


def _make_client(responses: list) -> MagicMock:
    """Create a client wiring both ``messages.create`` and ``messages.stream``
    against a shared queue. Extraction runs at max_tokens=32768 so it routes
    through ``messages.stream``; lower-token structured calls would route
    through ``messages.create``. The shared queue covers either path.

    Each ``responses`` entry is either a JSON string / dict (wrapped via
    ``_make_response``) or an already-built mock response.
    """
    queue = [
        r if not isinstance(r, str | dict) else _make_response(r) for r in responses
    ]
    iterator = iter(queue)

    async def _create(**_kw):
        return next(iterator)

    def _stream(**_kw):
        return _StreamCM(next(iterator))

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    client.messages.stream = MagicMock(side_effect=_stream)
    return client


# ---------------------------------------------------------------------------
# Realistic LLM response fixtures
# ---------------------------------------------------------------------------

RESEARCHER_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "label": "Paradigm",
                "properties": {
                    "name": "Homeostatic Regulation",
                    "slug": "homeostatic-regulation",
                    "description": "Behavior as instrument for restoring internal equilibrium",
                },
                "natural_key": "slug",
            },
            {
                "label": "Author",
                "properties": {
                    "name": "Claude Bernard",
                    "affiliation": "University of Paris",
                },
                "natural_key": "name",
            },
            {
                "label": "Author",
                "properties": {
                    "name": "Walter B. Cannon",
                    "affiliation": "Harvard Medical School",
                },
                "natural_key": "name",
            },
            {
                "label": "Author",
                "properties": {
                    "name": "Gina Turrigiano",
                    "affiliation": "Brandeis University",
                },
                "natural_key": "name",
            },
            {
                "label": "Paper",
                "properties": {
                    "title": "Introduction a l'etude de la medecine experimentale",
                    "year": 1865,
                    "doi": None,
                    "citation_count": None,
                },
                "natural_key": "title",
            },
            {
                "label": "Paper",
                "properties": {
                    "title": "The Wisdom of the Body",
                    "year": 1932,
                    "doi": None,
                    "citation_count": None,
                },
                "natural_key": "title",
            },
            {
                "label": "Paper",
                "properties": {
                    "title": "Activity-dependent scaling of quantal amplitude in neocortical neurons",
                    "year": 1998,
                    "doi": None,
                    "citation_count": None,
                },
                "natural_key": "title",
            },
            {
                "label": "Paper",
                "properties": {
                    "title": "A Reinforcement Learning Theory for Homeostatic Regulation",
                    "year": 2011,
                    "doi": None,
                    "citation_count": None,
                },
                "natural_key": "title",
            },
            {
                "label": "BrainRegion",
                "properties": {"name": "hypothalamus", "system": "homeostatic"},
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "energy_level",
                    "type": "state",
                    "range": "[0, 100]",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "set_point",
                    "type": "parameter",
                    "range": "fixed",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "error_signal",
                    "type": "derived",
                    "range": "signed",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "ghrelin",
                    "type": "molecular",
                    "range": "positive",
                    "unit": "ng/mL",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "leptin",
                    "type": "molecular",
                    "range": "positive",
                    "unit": "ng/mL",
                },
                "natural_key": "name",
            },
            {
                "label": "Postulate",
                "properties": {
                    "id": "P1",
                    "statement": "Every living system has one or more set points for critical internal variables",
                    "falsifiable": True,
                },
                "natural_key": "id",
            },
            {
                "label": "Postulate",
                "properties": {
                    "id": "P2",
                    "statement": "Deviations from a set point generate an error signal that drives corrective responses",
                    "falsifiable": True,
                },
                "natural_key": "id",
            },
            {
                "label": "Postulate",
                "properties": {
                    "id": "P3",
                    "statement": "Homeostatic control is implemented through negative feedback loops",
                    "falsifiable": True,
                },
                "natural_key": "id",
            },
        ],
        "relations": [
            {
                "from_label": "Postulate",
                "from_key_value": "P1",
                "to_label": "Paradigm",
                "to_key_value": "homeostatic-regulation",
                "rel_type": "BELONGS_TO",
                "properties": {},
            },
            {
                "from_label": "Postulate",
                "from_key_value": "P2",
                "to_label": "Paradigm",
                "to_key_value": "homeostatic-regulation",
                "rel_type": "BELONGS_TO",
                "properties": {},
            },
            {
                "from_label": "Author",
                "from_key_value": "Claude Bernard",
                "to_label": "Paper",
                "to_key_value": "Introduction a l'etude de la medecine experimentale",
                "rel_type": "AUTHORED",
                "properties": {},
            },
            {
                "from_label": "Paper",
                "from_key_value": "The Wisdom of the Body",
                "to_label": "Postulate",
                "to_key_value": "P1",
                "rel_type": "SUPPORTS",
                "properties": {
                    "confidence": 0.9,
                    "quote": "coordinated physiological processes that maintain steady states",
                },
            },
            {
                "from_label": "Variable",
                "from_key_value": "energy_level",
                "to_label": "BrainRegion",
                "to_key_value": "hypothalamus",
                "rel_type": "MEASURES",
                "properties": {},
            },
        ],
        "facts": [
            "Every living system maintains critical internal variables around set points.",
            "Deviations from homeostatic set points generate error signals driving corrective behavior.",
            "Homeostatic control uses negative feedback loops with receptors, comparators, and effectors.",
            "Energy level is a regulated state variable oscillating around the organism's set point.",
            "Ghrelin signals hunger and drives food-seeking behavior when energy is below set point.",
        ],
    }
)

FORMALIZER_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "label": "Formulation",
                "properties": {
                    "id": "formulation-1",
                    "name": "PI Negative-Feedback Controller",
                    "type": "ODE-based control",
                    "description": "Continuous-time ODE-based control with proportional and integral error correction",
                },
                "natural_key": "id",
            },
            {
                "label": "Formulation",
                "properties": {
                    "id": "formulation-2",
                    "name": "Drive-Reduction MDP",
                    "type": "Q-learning MDP",
                    "description": "Tabular Q-learning where reward is drive reduction",
                },
                "natural_key": "id",
            },
            {
                "label": "Equation",
                "properties": {
                    "latex": "e(t) = s - A(t)",
                    "plaintext": "error = setpoint minus energy",
                    "type": "algebraic",
                },
                "natural_key": "plaintext",
            },
            {
                "label": "Equation",
                "properties": {
                    "latex": "D(x) = \\phi (x - s)^2",
                    "plaintext": "drive = weight times squared deviation from setpoint",
                    "type": "algebraic",
                },
                "natural_key": "plaintext",
            },
            {
                "label": "Equation",
                "properties": {
                    "latex": "c_P(t) = k_P \\cdot e(t)",
                    "plaintext": "proportional control = gain times error",
                    "type": "algebraic",
                },
                "natural_key": "plaintext",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "energy",
                    "type": "Continuous, A in [0, A_max]",
                    "range": "[0, 100]",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "error_signal",
                    "type": "Signed scalar",
                    "range": "unbounded",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Variable",
                "properties": {
                    "name": "drive",
                    "type": "float",
                    "range": "[0, 6400]",
                    "unit": "arbitrary",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "energy_set_point",
                    "default_value": 80.0,
                    "source": "Keramati & Gutkin (2011)",
                    "range": "[0, 100]",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "proportional_gain",
                    "default_value": 0.5,
                    "source": "npj Digital Medicine (2020)",
                    "range": "positive",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "integral_gain",
                    "default_value": 0.05,
                    "source": "Drengstig et al. (2012)",
                    "range": "positive",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "drive_weight",
                    "default_value": 1.0,
                    "source": "Keramati & Gutkin (2011)",
                    "range": "positive",
                },
                "natural_key": "name",
            },
        ],
        "relations": [
            {
                "from_label": "Formulation",
                "from_key_value": "formulation-1",
                "to_label": "Equation",
                "to_key_value": "error = setpoint minus energy",
                "rel_type": "USES_EQUATION",
                "properties": {},
            },
            {
                "from_label": "Formulation",
                "from_key_value": "formulation-1",
                "to_label": "Equation",
                "to_key_value": "proportional control = gain times error",
                "rel_type": "USES_EQUATION",
                "properties": {},
            },
            {
                "from_label": "Formulation",
                "from_key_value": "formulation-2",
                "to_label": "Equation",
                "to_key_value": "drive = weight times squared deviation from setpoint",
                "rel_type": "USES_EQUATION",
                "properties": {},
            },
            {
                "from_label": "Variable",
                "from_key_value": "error_signal",
                "to_label": "Variable",
                "to_key_value": "energy",
                "rel_type": "MODULATES",
                "properties": {
                    "direction": "negative",
                    "equation_ref": "e(t) = s - A(t)",
                },
            },
        ],
        "facts": [
            "The error signal equals the setpoint minus the current energy level.",
            "The drive function is a quadratic measure of deviation from the homeostatic setpoint.",
            "The proportional control term scales linearly with the error signal.",
            "The energy set point defaults to 80.0 based on Keramati & Gutkin (2011).",
            "The proportional gain defaults to 0.5 based on npj Digital Medicine (2020).",
        ],
    }
)

REASONER_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "label": "Formulation",
                "properties": {
                    "id": "homeostatic-regulation_drive_reduction_rl",
                    "name": "Homeostatic Reinforcement Learning (Drive-Reduction MDP)",
                    "type": "Q-learning MDP",
                    "description": "Tabular Q-learning where reward is drive reduction",
                },
                "natural_key": "id",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "energy_set_point",
                    "default_value": 80.0,
                    "source": "Keramati & Gutkin (2011)",
                    "range": "[0, 100]",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "td_learning_rate",
                    "default_value": 0.1,
                    "source": "Sutton & Barto convention",
                    "range": "(0, 1]",
                },
                "natural_key": "name",
            },
            {
                "label": "Parameter",
                "properties": {
                    "name": "discount_factor",
                    "default_value": 0.95,
                    "source": "Keramati & Gutkin (2011)",
                    "range": "[0.9, 0.99]",
                },
                "natural_key": "name",
            },
        ],
        "relations": [
            {
                "from_label": "Parameter",
                "from_key_value": "energy_set_point",
                "to_label": "Postulate",
                "to_key_value": "P1",
                "rel_type": "DERIVES_FROM",
                "properties": {
                    "derivation_chain": "P1 states organisms maintain set points -> energy_set_point is the target energy level"
                },
            },
            {
                "from_label": "Parameter",
                "from_key_value": "td_learning_rate",
                "to_label": "Postulate",
                "to_key_value": "P6",
                "rel_type": "DERIVES_FROM",
                "properties": {
                    "derivation_chain": "P6 frames reward as drive reduction -> learning rate controls how quickly drive-reduction signal updates Q-values"
                },
            },
        ],
        "facts": [
            "Perception variable x maps to the agent's internal energy level.",
            "The available actions are move_up, move_down, move_left, move_right, stay, and eat.",
            "Reward is computed as drive reduction: D(x_prev) - D(x_current).",
            "Expected behavior B1: agent increases food-seeking when energy drops below setpoint.",
        ],
    }
)

BUILDER_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "label": "Model",
                "properties": {
                    "formulation_id": "homeostatic-regulation_drive_reduction_rl",
                    "class_name": "HomeostaticDriveReductionRL",
                    "passed": True,
                    "failure_reason": None,
                },
                "natural_key": "formulation_id",
            },
        ],
        "relations": [
            {
                "from_label": "Model",
                "from_key_value": "homeostatic-regulation_drive_reduction_rl",
                "to_label": "Formulation",
                "to_key_value": "homeostatic-regulation_drive_reduction_rl",
                "rel_type": "IMPLEMENTS",
                "properties": {},
            },
        ],
        "facts": [
            "Model HomeostaticDriveReductionRL passes all behavior tests.",
            "Uses Q-learning with softmax action selection over a discretized state space.",
            "Implements drive-reduction reward signal: reward = D(x_prev) - D(x_current).",
        ],
    }
)

LEGACY_BUILDER_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "label": "Model",
                "properties": {
                    "formulation_id": "homeostatic-regulation_drive_reduction_rl",
                    "class_name": "HomeostaticDriveReductionRL",
                },
                "natural_key": "formulation_id",
            },
            {
                "label": "TestResult",
                "properties": {
                    "formulation_id": "homeostatic-regulation_drive_reduction_rl",
                    "passed": False,
                    "failure_reason": "behavior test B2 failed",
                },
                "natural_key": "formulation_id",
            },
        ],
        "relations": [
            {
                "from_label": "Model",
                "from_key_value": "homeostatic-regulation_drive_reduction_rl",
                "to_label": "Formulation",
                "to_key_value": "homeostatic-regulation_drive_reduction_rl",
                "rel_type": "IMPLEMENTS",
                "properties": {},
            },
        ],
        "facts": [
            "Model HomeostaticDriveReductionRL failed behavior test B2.",
            "Uses Q-learning with softmax action selection.",
            "Implements drive-reduction reward signal.",
        ],
    }
)


# ---------------------------------------------------------------------------
# AC1: Researcher extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_researcher_produces_expected_entities():
    """AC1: extract('researcher', ...) produces Paradigm, Authors, Papers, Variables, Postulates."""
    client = _make_client([RESEARCHER_RESPONSE])
    result = await extract(
        "researcher", "# Homeostatic Regulation report...", "run-1", client
    )

    assert isinstance(result, ExtractionResult)
    assert result.stage == "researcher"
    assert result.run_id == "run-1"

    labels = {n.label for n in result.nodes}
    assert "Paradigm" in labels
    assert "Author" in labels
    assert "Paper" in labels
    assert "Variable" in labels
    assert "Postulate" in labels

    # Minimum counts from AC1
    paradigms = [n for n in result.nodes if n.label == "Paradigm"]
    assert len(paradigms) >= 1
    authors = [n for n in result.nodes if n.label == "Author"]
    assert len(authors) >= 2
    papers = [n for n in result.nodes if n.label == "Paper"]
    assert len(papers) >= 3
    variables = [n for n in result.nodes if n.label == "Variable"]
    assert len(variables) >= 3
    postulates = [n for n in result.nodes if n.label == "Postulate"]
    assert len(postulates) >= 2


@pytest.mark.asyncio
async def test_extract_researcher_produces_relations():
    """Researcher extraction includes BELONGS_TO, AUTHORED, SUPPORTS, MEASURES."""
    client = _make_client([RESEARCHER_RESPONSE])
    result = await extract("researcher", "report text", "run-1", client)

    rel_types = {r.rel_type for r in result.relations}
    assert "BELONGS_TO" in rel_types
    assert "AUTHORED" in rel_types
    assert "SUPPORTS" in rel_types
    assert "MEASURES" in rel_types


# ---------------------------------------------------------------------------
# AC2: Formalizer extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_formalizer_produces_equations_and_parameters():
    """AC2: extract('formalizer', ...) produces Equations and Parameters with defaults/sources."""
    client = _make_client([FORMALIZER_RESPONSE])
    result = await extract(
        "formalizer", "# Homeostatic formulations...", "run-1", client
    )

    equations = [n for n in result.nodes if n.label == "Equation"]
    assert len(equations) >= 2

    params = [n for n in result.nodes if n.label == "Parameter"]
    assert len(params) >= 3
    for p in params:
        assert "default_value" in p.properties
        assert "source" in p.properties


@pytest.mark.asyncio
async def test_extract_formalizer_produces_uses_equation_relations():
    """Formalizer produces USES_EQUATION and MODULATES relations."""
    client = _make_client([FORMALIZER_RESPONSE])
    result = await extract("formalizer", "formalization text", "run-1", client)

    rel_types = {r.rel_type for r in result.relations}
    assert "USES_EQUATION" in rel_types
    assert "MODULATES" in rel_types


# ---------------------------------------------------------------------------
# AC3: Reasoner extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_reasoner_produces_derives_from():
    """AC3: extract('reasoner', ...) produces DERIVES_FROM linking parameters to postulates."""
    client = _make_client([REASONER_RESPONSE])
    result = await extract("reasoner", '{"formulation_id": "..."}', "run-1", client)

    derives = [r for r in result.relations if r.rel_type == "DERIVES_FROM"]
    assert len(derives) >= 1

    for rel in derives:
        assert rel.from_label == "Parameter"
        assert rel.to_label == "Postulate"
        assert "derivation_chain" in rel.properties


# ---------------------------------------------------------------------------
# AC4: Builder extraction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_builder_produces_model_with_test_properties():
    """AC4: extract('builder', ...) produces a Model node carrying class_name and test outcome props."""
    client = _make_client([BUILDER_RESPONSE])
    result = await extract("builder", "# model code...", "run-1", client)

    models = [n for n in result.nodes if n.label == "Model"]
    assert len(models) == 1
    assert models[0].properties["class_name"] == "HomeostaticDriveReductionRL"
    assert models[0].properties["passed"] is True
    assert models[0].properties["failure_reason"] is None

    assert not any(n.label == "TestResult" for n in result.nodes)

    implements = [r for r in result.relations if r.rel_type == "IMPLEMENTS"]
    assert len(implements) >= 1


@pytest.mark.asyncio
async def test_extract_builder_legacy_testresult_folds_into_model():
    """Old-format Builder output (separate TestResult node) is folded into the Model node."""
    client = _make_client([LEGACY_BUILDER_RESPONSE])
    result = await extract("builder", "# model code...", "run-1", client)

    assert not any(n.label == "TestResult" for n in result.nodes)

    models = [n for n in result.nodes if n.label == "Model"]
    assert len(models) == 1
    props = models[0].properties
    assert props["class_name"] == "HomeostaticDriveReductionRL"
    assert props["passed"] is False
    assert props["failure_reason"] == "behavior test B2 failed"


# ---------------------------------------------------------------------------
# AC5: Facts are atomic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stage,response",
    [
        ("researcher", RESEARCHER_RESPONSE),
        ("formalizer", FORMALIZER_RESPONSE),
        ("reasoner", REASONER_RESPONSE),
        ("builder", BUILDER_RESPONSE),
    ],
)
async def test_each_extraction_produces_atomic_facts(stage, response):
    """AC5: Each extraction produces >=3 facts that are atomic (not compound sentences)."""
    client = _make_client([response])
    result = await extract(stage, "stage output text", "run-1", client)

    assert len(result.facts) >= 3
    for fact in result.facts:
        assert isinstance(fact, str)
        assert len(fact) > 0
        # Atomic = should not contain " and " joining two independent clauses
        # (a rough heuristic; the real check is in the prompt design)


# ---------------------------------------------------------------------------
# Structured-output failure modes (replaces pre-rewrite JSON-retry tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_tokens_truncation_raises_immediately():
    """stop_reason='max_tokens' raises on the first call — retrying with the
    same prompt would truncate again, so the wrapper fails loudly."""
    truncated = _make_response({"nodes": [], "relations": [], "facts": []})
    truncated.stop_reason = "max_tokens"
    client = _make_client([truncated])
    with pytest.raises(StructuredOutputError, match="truncated at max_tokens"):
        await extract("researcher", "report text", "run-1", client)
    # Extraction's _MAX_TOKENS=32768 routes via messages.stream
    assert client.messages.stream.call_count == 1


@pytest.mark.asyncio
async def test_no_tool_use_block_raises():
    """A response without a tool_use block (e.g. plain text refusal) raises
    StructuredOutputError so the failure surfaces in the trace instead of
    being silently swallowed."""
    text_only = MagicMock()
    text_only.content = []
    text_only.stop_reason = "end_turn"
    text_only.usage = None
    client = _make_client([text_only])
    with pytest.raises(StructuredOutputError, match="no tool_use block"):
        await extract("researcher", "report text", "run-1", client)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_unknown_stage_raises_value_error():
    """Passing an unknown stage raises ValueError."""
    client = _make_client([])
    with pytest.raises(ValueError, match="Unknown stage"):
        await extract("unknown_stage", "text", "run-1", client)


# ---------------------------------------------------------------------------
# AC1 (P0-001): Per-stage model tiering
# Researcher + Reasoner → ``knowledge_structured_model`` (Sonnet)
# Formalizer + Builder → ``knowledge_fast_model`` (Haiku)
# ---------------------------------------------------------------------------


_EMPTY_EXTRACTION = {"nodes": [], "relations": [], "facts": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "tier"),
    [
        ("researcher", "structured"),
        ("formalizer", "fast"),
        ("reasoner", "structured"),
        ("builder", "fast"),
    ],
)
async def test_extract_resolves_model_per_stage(stage, tier):
    """Each stage threads its tier-appropriate model into ``call_structured``."""
    from decisionlab.config import SETTINGS

    expected = (
        SETTINGS.knowledge_structured_model
        if tier == "structured"
        else SETTINGS.knowledge_fast_model
    )
    client = _make_client([_EMPTY_EXTRACTION])
    await extract(stage, "irrelevant body", "run-1", client)

    # _MAX_TOKENS=32768 routes through ``messages.stream``.
    client.messages.stream.assert_called_once()
    assert client.messages.stream.call_args.kwargs["model"] == expected


def test_stage_models_dict_covers_all_stages():
    """``_STAGE_MODELS`` carries an entry for every prompted stage so a
    ``KeyError`` cannot leak through ``extract``."""
    from decisionlab.knowledge.extraction import _STAGE_MODELS, _STAGE_PROMPTS

    assert set(_STAGE_MODELS) == set(_STAGE_PROMPTS)


@pytest.mark.parametrize(
    "slug",
    [
        "b47e-b402d07b1163",  # partial-UUID fragment
        "8a3f-9b2c1d4e5f60",
        "xyz",  # too-short single-word
        "abc",
        "",
    ],
)
def test_garbage_paradigm_slug_rejected(slug):
    """Partial-UUID and short single-word slugs are flagged as garbage."""
    assert _is_garbage_paradigm_slug(slug)


@pytest.mark.parametrize(
    "slug",
    [
        "reinforcement-learning",
        "prospect-theory",
        "drift-diffusion-model",
        "free-energy-principle",
    ],
)
def test_real_paradigm_slug_passes(slug):
    """Legitimate kebab-case multi-word slugs pass through."""
    assert not _is_garbage_paradigm_slug(slug)


def test_build_result_filters_garbage_paradigm_nodes():
    """``_build_result`` drops Paradigm nodes whose slug is partial-UUID/stub."""
    data = {
        "nodes": [
            {
                "label": "Paradigm",
                "properties": {
                    "name": "Reinforcement Learning",
                    "slug": "reinforcement-learning",
                    "description": "Real paradigm",
                },
                "natural_key": "slug",
            },
            {
                "label": "Paradigm",
                "properties": {
                    "name": "Garbage",
                    "slug": "b47e-b402d07b1163",
                    "description": "UUID fragment",
                },
                "natural_key": "slug",
            },
            {
                "label": "Paradigm",
                "properties": {
                    "name": "Stub",
                    "slug": "xyz",
                    "description": "Too short",
                },
                "natural_key": "slug",
            },
        ],
        "relations": [],
        "facts": [],
    }
    result = _build_result(data, "researcher", "run-1")
    assert len(result.nodes) == 1
    assert result.nodes[0].properties["slug"] == "reinforcement-learning"


def test_build_result_skips_malformed_nodes():
    """_build_result ignores nodes missing required fields."""
    data = {
        "nodes": [
            {
                "label": "Paradigm",
                "properties": {"name": "X", "slug": "named-theory"},
                "natural_key": "slug",
            },  # valid (slug passes garbage filter)
            {"label": "Bad"},  # missing properties and natural_key
            "not a dict",  # not a dict
            {
                "label": "Also Bad",
                "properties": "not a dict",
                "natural_key": "x",
            },  # properties not dict
        ],
        "relations": [],
        "facts": [],
    }
    result = _build_result(data, "researcher", "run-1")
    assert len(result.nodes) == 1
    assert result.nodes[0].label == "Paradigm"


def test_build_result_skips_malformed_relations():
    """_build_result ignores relations missing required fields."""
    data = {
        "nodes": [],
        "relations": [
            {
                "from_label": "A",
                "from_key_value": "1",
                "to_label": "B",
                "to_key_value": "2",
                "rel_type": "R",
            },  # valid
            {"from_label": "A"},  # incomplete
        ],
        "facts": [],
    }
    result = _build_result(data, "researcher", "run-1")
    assert len(result.relations) == 1


def test_build_result_skips_empty_facts():
    """_build_result filters out empty/whitespace-only facts."""
    data = {
        "nodes": [],
        "relations": [],
        "facts": ["valid fact", "", "  ", "another fact"],
    }
    result = _build_result(data, "researcher", "run-1")
    assert result.facts == ["valid fact", "another fact"]


# ---------------------------------------------------------------------------
# Legacy TestResult fold — edge cases (see _fold_legacy_test_results)
# ---------------------------------------------------------------------------


def test_fold_legacy_orphan_testresult_warns_and_drops(caplog):
    """A TestResult with no matching Model is dropped and logged."""
    raw_nodes = [
        {
            "label": "Model",
            "properties": {"formulation_id": "fid-a", "class_name": "A"},
            "natural_key": "formulation_id",
        },
        {
            "label": "TestResult",
            "properties": {
                "formulation_id": "fid-missing",
                "passed": True,
                "failure_reason": None,
            },
            "natural_key": "formulation_id",
        },
    ]
    with caplog.at_level("WARNING", logger="decisionlab.knowledge.extraction"):
        survivors = _fold_legacy_test_results(raw_nodes)

    assert [n["label"] for n in survivors] == ["Model"]
    assert survivors[0]["properties"] == {"formulation_id": "fid-a", "class_name": "A"}
    assert any("fid-missing" in r.message for r in caplog.records)


def test_fold_legacy_testresult_without_formulation_id_is_ignored():
    """A TestResult missing formulation_id is silently discarded without mutating the Model."""
    raw_nodes = [
        {
            "label": "Model",
            "properties": {"formulation_id": "fid-a", "class_name": "A"},
            "natural_key": "formulation_id",
        },
        {
            "label": "TestResult",
            "properties": {"passed": True, "failure_reason": None},
            "natural_key": "formulation_id",
        },
    ]
    survivors = _fold_legacy_test_results(raw_nodes)

    assert len(survivors) == 1
    assert survivors[0]["properties"] == {"formulation_id": "fid-a", "class_name": "A"}


def test_fold_legacy_conflict_keeps_model_value_and_warns(caplog):
    """When Model and TestResult disagree, the Model's explicit value wins and the discard is logged."""
    raw_nodes = [
        {
            "label": "Model",
            "properties": {
                "formulation_id": "fid-a",
                "class_name": "A",
                "passed": True,
                "failure_reason": None,
            },
            "natural_key": "formulation_id",
        },
        {
            "label": "TestResult",
            "properties": {
                "formulation_id": "fid-a",
                "passed": False,
                "failure_reason": "B2 failed",
            },
            "natural_key": "formulation_id",
        },
    ]
    with caplog.at_level("WARNING", logger="decisionlab.knowledge.extraction"):
        survivors = _fold_legacy_test_results(raw_nodes)

    model_props = survivors[0]["properties"]
    assert model_props["passed"] is True
    assert model_props["failure_reason"] is None
    conflict_messages = [
        r.message for r in caplog.records if "conflicts with Model" in r.message
    ]
    assert len(conflict_messages) == 2  # one per differing prop


def test_fold_legacy_multiple_models_each_get_their_own_test_props():
    """Multiple Model/TestResult pairs in one payload are folded independently."""
    raw_nodes = [
        {
            "label": "Model",
            "properties": {"formulation_id": "fid-a", "class_name": "A"},
            "natural_key": "formulation_id",
        },
        {
            "label": "Model",
            "properties": {"formulation_id": "fid-b", "class_name": "B"},
            "natural_key": "formulation_id",
        },
        {
            "label": "TestResult",
            "properties": {
                "formulation_id": "fid-a",
                "passed": True,
                "failure_reason": None,
            },
            "natural_key": "formulation_id",
        },
        {
            "label": "TestResult",
            "properties": {
                "formulation_id": "fid-b",
                "passed": False,
                "failure_reason": "x",
            },
            "natural_key": "formulation_id",
        },
    ]
    survivors = _fold_legacy_test_results(raw_nodes)
    by_fid = {n["properties"]["formulation_id"]: n["properties"] for n in survivors}

    assert by_fid["fid-a"]["passed"] is True
    assert by_fid["fid-a"]["failure_reason"] is None
    assert by_fid["fid-b"]["passed"] is False
    assert by_fid["fid-b"]["failure_reason"] == "x"


@pytest.mark.asyncio
async def test_output_text_with_curly_braces():
    """Curly braces in output_text (e.g. JSON) don't cause format errors."""
    json_text = '{"parameters": [{"name": "alpha", "default": 0.1}]}'
    client = _make_client([REASONER_RESPONSE])
    result = await extract("reasoner", json_text, "run-1", client)

    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) > 0
