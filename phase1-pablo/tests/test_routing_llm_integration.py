"""Integration tests for routing LLM — calls real Haiku API.

Run with:  uv run pytest tests/test_routing_llm_integration.py -v
Requires:  ANTHROPIC_API_KEY set in environment or .env
"""

from __future__ import annotations

import os

import pytest
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from decisionlab.routing_llm import classify_feedback

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)

PARADIGMS = ["homeostatic-regulation", "prospect-theory", "reinforcement-learning"]


@pytest.fixture
def client() -> AsyncAnthropic:
    return AsyncAnthropic()


# ---------------------------------------------------------------------------
# Builder — code bugs, test failures, import errors
# ---------------------------------------------------------------------------


class TestRouteToBuilder:
    async def test_test_failure(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The tests crash because the code has a TypeError — the decide() method returns a string 'up' instead of an Action object. It's a bug in the model code, the return type is wrong.",
            paradigms=PARADIGMS,
            build_output="FAILED test_decide - TypeError: expected Action, got str. File homeostatic_regulation_model.py line 52: return 'up'",
        )
        assert result.target == "builder"

    async def test_import_error(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The homeostatic model can't import numpy, it crashes on startup",
            paradigms=PARADIGMS,
            build_output="ImportError: No module named 'numpy' in homeostatic_regulation_model.py line 3",
        )
        assert result.target == "builder"

    async def test_code_bug(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="There's an IndexError in the homeostatic-regulation model when the food_sources list is empty",
            paradigms=PARADIGMS,
            build_output="IndexError: list index out of range at homeostatic_regulation_model.py:47",
        )
        assert result.target == "builder"


# ---------------------------------------------------------------------------
# Reasoner — spec problems, wrong rules, bad pseudocode
# ---------------------------------------------------------------------------


class TestRouteToReasoner:
    async def test_wrong_rule(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The decision rule in the homeostatic-regulation spec is wrong — it says the agent should move away from food when hungry, but it should move toward food",
            paradigms=PARADIGMS,
            spec_content='{"name": "homeostatic_basic", "paradigm": "homeostatic-regulation", "rules": [{"condition": "hunger > threshold", "action": "move_away_from_food"}]}',
        )
        assert result.target == "reasoner"

    async def test_bad_env_mapping(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The spec for prospect-theory maps the 'risk' variable to the wrong perception field — it should read from 'danger_level' not 'food_sources'",
            paradigms=PARADIGMS,
            spec_content='{"name": "prospect_theory_basic", "paradigm": "prospect-theory", "env_mapping": {"risk": "food_sources"}}',
        )
        assert result.target == "reasoner"

    async def test_incorrect_pseudocode(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The pseudocode in the reinforcement-learning spec has the reward update backwards — it should add the reward, not subtract it",
            paradigms=PARADIGMS,
            spec_content='{"name": "rl_basic", "paradigm": "reinforcement-learning", "pseudocode": "Q[s,a] = Q[s,a] - alpha * reward"}',
        )
        assert result.target == "reasoner"


# ---------------------------------------------------------------------------
# Formalizer — wrong equations, missing variables, bad math model
# ---------------------------------------------------------------------------


class TestRouteToFormalizer:
    async def test_wrong_equation(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The mathematical formulation for homeostatic-regulation uses a linear equation for the drive function, but it should be exponential decay: drive = e^(-k*deficit) not drive = k*deficit",
            paradigms=PARADIGMS,
        )
        assert result.target == "formalizer"

    async def test_missing_variable(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The prospect-theory formalization is missing the reference point variable — prospect theory fundamentally requires a reference point to compute gains and losses",
            paradigms=PARADIGMS,
        )
        assert result.target == "formalizer"


# ---------------------------------------------------------------------------
# Researcher — bad theory, missing research, wrong postulates
# ---------------------------------------------------------------------------


class TestRouteToResearcher:
    async def test_missing_theory(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The research on homeostatic-regulation completely misses allostasis — it only covers classic homeostasis but modern literature emphasizes allostatic regulation as the core mechanism",
            paradigms=PARADIGMS,
        )
        assert result.target == "researcher"

    async def test_wrong_postulates(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The foundational assumptions researched for prospect-theory are wrong — it attributes the paradigm to Skinner instead of Kahneman and Tversky, and confuses it with operant conditioning",
            paradigms=PARADIGMS,
        )
        assert result.target == "researcher"


# ---------------------------------------------------------------------------
# Paradigm identification
# ---------------------------------------------------------------------------


class TestParadigmIdentification:
    async def test_identifies_paradigm_from_feedback(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The prospect-theory model has a bug — the value function crashes with a division by zero",
            paradigms=PARADIGMS,
            build_output="ZeroDivisionError in prospect_theory_model.py:23",
        )
        assert result.paradigm == "prospect-theory"

    async def test_identifies_different_paradigm(self, client: AsyncAnthropic):
        result = await classify_feedback(
            client=client,
            feedback="The reinforcement-learning agent's Q-table update is wrong in the spec",
            paradigms=PARADIGMS,
            spec_content='{"paradigm": "reinforcement-learning", "pseudocode": "Q[s,a] -= reward"}',
        )
        assert result.paradigm == "reinforcement-learning"
