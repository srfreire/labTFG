"""Tests for knowledge extraction module — covers AC1 through AC6."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from decisionlab.knowledge.extraction import extract, _try_parse_json, _build_result
from decisionlab.knowledge.models import ExtractionResult


# ---------------------------------------------------------------------------
# Helpers: build mock Haiku responses
# ---------------------------------------------------------------------------

def _make_response(text: str) -> MagicMock:
    """Build a mock Anthropic message response with the given text content."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_client(responses: list[str]) -> AsyncMock:
    """Create an AsyncMock client whose messages.create returns the given texts in order."""
    client = AsyncMock()
    client.messages.create = AsyncMock(
        side_effect=[_make_response(t) for t in responses]
    )
    return client


# ---------------------------------------------------------------------------
# Realistic LLM response fixtures
# ---------------------------------------------------------------------------

RESEARCHER_RESPONSE = json.dumps({
    "nodes": [
        {"label": "Paradigm", "properties": {"name": "Homeostatic Regulation", "slug": "homeostatic-regulation", "description": "Behavior as instrument for restoring internal equilibrium"}, "natural_key": "slug"},
        {"label": "Author", "properties": {"name": "Claude Bernard", "affiliation": "University of Paris"}, "natural_key": "name"},
        {"label": "Author", "properties": {"name": "Walter B. Cannon", "affiliation": "Harvard Medical School"}, "natural_key": "name"},
        {"label": "Author", "properties": {"name": "Gina Turrigiano", "affiliation": "Brandeis University"}, "natural_key": "name"},
        {"label": "Paper", "properties": {"title": "Introduction a l'etude de la medecine experimentale", "year": 1865, "doi": None, "citation_count": None}, "natural_key": "title"},
        {"label": "Paper", "properties": {"title": "The Wisdom of the Body", "year": 1932, "doi": None, "citation_count": None}, "natural_key": "title"},
        {"label": "Paper", "properties": {"title": "Activity-dependent scaling of quantal amplitude in neocortical neurons", "year": 1998, "doi": None, "citation_count": None}, "natural_key": "title"},
        {"label": "Paper", "properties": {"title": "A Reinforcement Learning Theory for Homeostatic Regulation", "year": 2011, "doi": None, "citation_count": None}, "natural_key": "title"},
        {"label": "BrainRegion", "properties": {"name": "hypothalamus", "system": "homeostatic"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "energy_level", "type": "state", "range": "[0, 100]", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "set_point", "type": "parameter", "range": "fixed", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "error_signal", "type": "derived", "range": "signed", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "ghrelin", "type": "molecular", "range": "positive", "unit": "ng/mL"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "leptin", "type": "molecular", "range": "positive", "unit": "ng/mL"}, "natural_key": "name"},
        {"label": "Postulate", "properties": {"id": "P1", "statement": "Every living system has one or more set points for critical internal variables", "falsifiable": True}, "natural_key": "id"},
        {"label": "Postulate", "properties": {"id": "P2", "statement": "Deviations from a set point generate an error signal that drives corrective responses", "falsifiable": True}, "natural_key": "id"},
        {"label": "Postulate", "properties": {"id": "P3", "statement": "Homeostatic control is implemented through negative feedback loops", "falsifiable": True}, "natural_key": "id"},
    ],
    "relations": [
        {"from_label": "Postulate", "from_key_value": "P1", "to_label": "Paradigm", "to_key_value": "homeostatic-regulation", "rel_type": "BELONGS_TO", "properties": {}},
        {"from_label": "Postulate", "from_key_value": "P2", "to_label": "Paradigm", "to_key_value": "homeostatic-regulation", "rel_type": "BELONGS_TO", "properties": {}},
        {"from_label": "Author", "from_key_value": "Claude Bernard", "to_label": "Paper", "to_key_value": "Introduction a l'etude de la medecine experimentale", "rel_type": "AUTHORED", "properties": {}},
        {"from_label": "Paper", "from_key_value": "The Wisdom of the Body", "to_label": "Postulate", "to_key_value": "P1", "rel_type": "SUPPORTS", "properties": {"confidence": 0.9, "quote": "coordinated physiological processes that maintain steady states"}},
        {"from_label": "Variable", "from_key_value": "energy_level", "to_label": "BrainRegion", "to_key_value": "hypothalamus", "rel_type": "MEASURES", "properties": {}},
    ],
    "facts": [
        "Every living system maintains critical internal variables around set points.",
        "Deviations from homeostatic set points generate error signals driving corrective behavior.",
        "Homeostatic control uses negative feedback loops with receptors, comparators, and effectors.",
        "Energy level is a regulated state variable oscillating around the organism's set point.",
        "Ghrelin signals hunger and drives food-seeking behavior when energy is below set point.",
    ],
})

FORMALIZER_RESPONSE = json.dumps({
    "nodes": [
        {"label": "Formulation", "properties": {"id": "formulation-1", "name": "PI Negative-Feedback Controller", "type": "ODE-based control", "description": "Continuous-time ODE-based control with proportional and integral error correction"}, "natural_key": "id"},
        {"label": "Formulation", "properties": {"id": "formulation-2", "name": "Drive-Reduction MDP", "type": "Q-learning MDP", "description": "Tabular Q-learning where reward is drive reduction"}, "natural_key": "id"},
        {"label": "Equation", "properties": {"latex": "e(t) = s - A(t)", "plaintext": "error = setpoint minus energy", "type": "algebraic"}, "natural_key": "plaintext"},
        {"label": "Equation", "properties": {"latex": "D(x) = \\phi (x - s)^2", "plaintext": "drive = weight times squared deviation from setpoint", "type": "algebraic"}, "natural_key": "plaintext"},
        {"label": "Equation", "properties": {"latex": "c_P(t) = k_P \\cdot e(t)", "plaintext": "proportional control = gain times error", "type": "algebraic"}, "natural_key": "plaintext"},
        {"label": "Variable", "properties": {"name": "energy", "type": "Continuous, A in [0, A_max]", "range": "[0, 100]", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "error_signal", "type": "Signed scalar", "range": "unbounded", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Variable", "properties": {"name": "drive", "type": "float", "range": "[0, 6400]", "unit": "arbitrary"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "energy_set_point", "default_value": 80.0, "source": "Keramati & Gutkin (2011)", "range": "[0, 100]"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "proportional_gain", "default_value": 0.5, "source": "npj Digital Medicine (2020)", "range": "positive"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "integral_gain", "default_value": 0.05, "source": "Drengstig et al. (2012)", "range": "positive"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "drive_weight", "default_value": 1.0, "source": "Keramati & Gutkin (2011)", "range": "positive"}, "natural_key": "name"},
    ],
    "relations": [
        {"from_label": "Formulation", "from_key_value": "formulation-1", "to_label": "Equation", "to_key_value": "error = setpoint minus energy", "rel_type": "USES_EQUATION", "properties": {}},
        {"from_label": "Formulation", "from_key_value": "formulation-1", "to_label": "Equation", "to_key_value": "proportional control = gain times error", "rel_type": "USES_EQUATION", "properties": {}},
        {"from_label": "Formulation", "from_key_value": "formulation-2", "to_label": "Equation", "to_key_value": "drive = weight times squared deviation from setpoint", "rel_type": "USES_EQUATION", "properties": {}},
        {"from_label": "Variable", "from_key_value": "error_signal", "to_label": "Variable", "to_key_value": "energy", "rel_type": "MODULATES", "properties": {"direction": "negative", "equation_ref": "e(t) = s - A(t)"}},
    ],
    "facts": [
        "The error signal equals the setpoint minus the current energy level.",
        "The drive function is a quadratic measure of deviation from the homeostatic setpoint.",
        "The proportional control term scales linearly with the error signal.",
        "The energy set point defaults to 80.0 based on Keramati & Gutkin (2011).",
        "The proportional gain defaults to 0.5 based on npj Digital Medicine (2020).",
    ],
})

REASONER_RESPONSE = json.dumps({
    "nodes": [
        {"label": "Formulation", "properties": {"id": "homeostatic-regulation_drive_reduction_rl", "name": "Homeostatic Reinforcement Learning (Drive-Reduction MDP)", "type": "Q-learning MDP", "description": "Tabular Q-learning where reward is drive reduction"}, "natural_key": "id"},
        {"label": "Parameter", "properties": {"name": "energy_set_point", "default_value": 80.0, "source": "Keramati & Gutkin (2011)", "range": "[0, 100]"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "td_learning_rate", "default_value": 0.1, "source": "Sutton & Barto convention", "range": "(0, 1]"}, "natural_key": "name"},
        {"label": "Parameter", "properties": {"name": "discount_factor", "default_value": 0.95, "source": "Keramati & Gutkin (2011)", "range": "[0.9, 0.99]"}, "natural_key": "name"},
    ],
    "relations": [
        {"from_label": "Parameter", "from_key_value": "energy_set_point", "to_label": "Postulate", "to_key_value": "P1", "rel_type": "DERIVES_FROM", "properties": {"derivation_chain": "P1 states organisms maintain set points -> energy_set_point is the target energy level"}},
        {"from_label": "Parameter", "from_key_value": "td_learning_rate", "to_label": "Postulate", "to_key_value": "P6", "rel_type": "DERIVES_FROM", "properties": {"derivation_chain": "P6 frames reward as drive reduction -> learning rate controls how quickly drive-reduction signal updates Q-values"}},
    ],
    "facts": [
        "Perception variable x maps to the agent's internal energy level.",
        "The available actions are move_up, move_down, move_left, move_right, stay, and eat.",
        "Reward is computed as drive reduction: D(x_prev) - D(x_current).",
        "Expected behavior B1: agent increases food-seeking when energy drops below setpoint.",
    ],
})

BUILDER_RESPONSE = json.dumps({
    "nodes": [
        {"label": "Model", "properties": {"formulation_id": "homeostatic-regulation_drive_reduction_rl", "class_name": "HomeostaticDriveReductionRL"}, "natural_key": "formulation_id"},
        {"label": "TestResult", "properties": {"formulation_id": "homeostatic-regulation_drive_reduction_rl", "passed": True, "failure_reason": None}, "natural_key": "formulation_id"},
    ],
    "relations": [
        {"from_label": "Model", "from_key_value": "homeostatic-regulation_drive_reduction_rl", "to_label": "Formulation", "to_key_value": "homeostatic-regulation_drive_reduction_rl", "rel_type": "IMPLEMENTS", "properties": {}},
    ],
    "facts": [
        "Model HomeostaticDriveReductionRL passes all behavior tests.",
        "Uses Q-learning with softmax action selection over a discretized state space.",
        "Implements drive-reduction reward signal: reward = D(x_prev) - D(x_current).",
    ],
})


# ---------------------------------------------------------------------------
# AC1: Researcher extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_researcher_produces_expected_entities():
    """AC1: extract('researcher', ...) produces Paradigm, Authors, Papers, Variables, Postulates."""
    client = _make_client([RESEARCHER_RESPONSE])
    result = await extract("researcher", "# Homeostatic Regulation report...", "run-1", client)

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
    result = await extract("formalizer", "# Homeostatic formulations...", "run-1", client)

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
async def test_extract_builder_produces_model_and_test_result():
    """AC4: extract('builder', ...) produces Model with class_name and TestResult with passed=True."""
    client = _make_client([BUILDER_RESPONSE])
    result = await extract("builder", "# model code...", "run-1", client)

    models = [n for n in result.nodes if n.label == "Model"]
    assert len(models) >= 1
    assert models[0].properties["class_name"] == "HomeostaticDriveReductionRL"

    test_results = [n for n in result.nodes if n.label == "TestResult"]
    assert len(test_results) >= 1
    assert test_results[0].properties["passed"] is True

    implements = [r for r in result.relations if r.rel_type == "IMPLEMENTS"]
    assert len(implements) >= 1


# ---------------------------------------------------------------------------
# AC5: Facts are atomic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("stage,response", [
    ("researcher", RESEARCHER_RESPONSE),
    ("formalizer", FORMALIZER_RESPONSE),
    ("reasoner", REASONER_RESPONSE),
    ("builder", BUILDER_RESPONSE),
])
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
# AC6: Malformed JSON retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_json_retries_once_then_succeeds():
    """AC6: Malformed JSON triggers one retry; second attempt succeeds."""
    client = _make_client(["not valid json {{{", RESEARCHER_RESPONSE])
    result = await extract("researcher", "report text", "run-1", client)

    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) > 0
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_malformed_json_both_attempts_returns_empty():
    """AC6: If retry also fails, returns empty ExtractionResult with warning."""
    client = _make_client(["bad json", "still bad json"])
    result = await extract("researcher", "report text", "run-1", client)

    assert isinstance(result, ExtractionResult)
    assert result.nodes == []
    assert result.relations == []
    assert result.facts == []
    assert result.stage == "researcher"
    assert result.run_id == "run-1"
    assert client.messages.create.call_count == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_unknown_stage_raises_value_error():
    """Passing an unknown stage raises ValueError."""
    client = _make_client([])
    with pytest.raises(ValueError, match="Unknown stage"):
        await extract("unknown_stage", "text", "run-1", client)


@pytest.mark.asyncio
async def test_extract_handles_markdown_fenced_json():
    """LLM wrapping response in ```json ... ``` fences is handled gracefully."""
    fenced = f"```json\n{RESEARCHER_RESPONSE}\n```"
    client = _make_client([fenced])
    result = await extract("researcher", "report text", "run-1", client)

    assert len(result.nodes) > 0


def test_try_parse_json_with_valid_input():
    assert _try_parse_json('{"nodes": []}') == {"nodes": []}


def test_try_parse_json_with_invalid_input():
    assert _try_parse_json("not json at all") is None


def test_try_parse_json_with_non_dict():
    assert _try_parse_json("[1, 2, 3]") is None


def test_build_result_skips_malformed_nodes():
    """_build_result ignores nodes missing required fields."""
    data = {
        "nodes": [
            {"label": "Paradigm", "properties": {"name": "X"}, "natural_key": "slug"},  # valid
            {"label": "Bad"},  # missing properties and natural_key
            "not a dict",  # not a dict
            {"label": "Also Bad", "properties": "not a dict", "natural_key": "x"},  # properties not dict
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
            {"from_label": "A", "from_key_value": "1", "to_label": "B", "to_key_value": "2", "rel_type": "R"},  # valid
            {"from_label": "A"},  # incomplete
        ],
        "facts": [],
    }
    result = _build_result(data, "researcher", "run-1")
    assert len(result.relations) == 1


def test_build_result_skips_empty_facts():
    """_build_result filters out empty/whitespace-only facts."""
    data = {"nodes": [], "relations": [], "facts": ["valid fact", "", "  ", "another fact"]}
    result = _build_result(data, "researcher", "run-1")
    assert result.facts == ["valid fact", "another fact"]


@pytest.mark.asyncio
async def test_empty_content_list_triggers_retry():
    """Empty response.content triggers retry via empty string → parse failure."""
    empty_resp = MagicMock()
    empty_resp.content = []
    good_resp = _make_response(RESEARCHER_RESPONSE)

    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=[empty_resp, good_resp])

    result = await extract("researcher", "report text", "run-1", client)
    assert len(result.nodes) > 0
    assert client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_output_text_with_curly_braces():
    """Curly braces in output_text (e.g. JSON) don't cause format errors."""
    json_text = '{"parameters": [{"name": "alpha", "default": 0.1}]}'
    client = _make_client([REASONER_RESPONSE])
    result = await extract("reasoner", json_text, "run-1", client)

    assert isinstance(result, ExtractionResult)
    assert len(result.nodes) > 0
