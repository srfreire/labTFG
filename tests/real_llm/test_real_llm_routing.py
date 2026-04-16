"""Real-LLM tests for `decisionlab.routing_llm.classify_feedback`.

Verifies the Haiku-based feedback classifier routes free-form feedback to the
correct pipeline target (researcher / formalizer / reasoner / builder) for a
known paradigm.
"""

from __future__ import annotations

import pytest

from decisionlab.routing_llm import classify_feedback

PARADIGMS = ["homeostatic-regulation"]


@pytest.mark.asyncio
async def test_real_routes_code_bug_to_builder(real_anthropic_client):
    """A clear Python crash routes to 'builder'."""
    result = await classify_feedback(
        client=real_anthropic_client,
        feedback=(
            "The model crashes with TypeError when calling decide(): "
            "'str' object has no attribute 'name'. The action is returned "
            "as a string instead of an Action object."
        ),
        paradigms=PARADIGMS,
    )
    assert result.target == "builder"
    assert result.paradigm == "homeostatic-regulation"


@pytest.mark.asyncio
async def test_real_routes_spec_problem_to_reasoner(real_anthropic_client):
    """A reversed decision rule in the spec routes to 'reasoner'."""
    result = await classify_feedback(
        client=real_anthropic_client,
        feedback=(
            "The reasoner spec says the agent should move AWAY from food when hungry, "
            "but the correct behavior is to move TOWARD food. The math model itself is "
            "fine — the problem is in how the spec encodes the action selection rule."
        ),
        paradigms=PARADIGMS,
    )
    assert result.target == "reasoner"
    assert result.paradigm == "homeostatic-regulation"


@pytest.mark.asyncio
async def test_real_routes_math_problem_to_formalizer(real_anthropic_client):
    """Wrong functional form in equations routes to 'formalizer'."""
    result = await classify_feedback(
        client=real_anthropic_client,
        feedback=(
            "The drive equation uses a linear function dD/dt = -k*D, but it should be "
            "an exponential decay dD/dt = -k * exp(-D). The mathematical formulation "
            "is wrong even though the underlying theory is fine."
        ),
        paradigms=PARADIGMS,
    )
    assert result.target == "formalizer"
    assert result.paradigm == "homeostatic-regulation"


@pytest.mark.asyncio
async def test_real_routes_theory_gap_to_researcher(real_anthropic_client):
    """Missing core theory routes to 'researcher'."""
    result = await classify_feedback(
        client=real_anthropic_client,
        feedback=(
            "The research completely misses the allostasis literature (Sterling, McEwen). "
            "It only covers classic homeostasis from Cannon. We need the broader "
            "theoretical foundation that includes predictive regulation."
        ),
        paradigms=PARADIGMS,
    )
    assert result.target == "researcher"
    assert result.paradigm == "homeostatic-regulation"


@pytest.mark.asyncio
async def test_real_routing_returns_paradigm_from_provided_list(real_anthropic_client):
    """When multiple paradigms are listed, the LLM picks the relevant one."""
    paradigms = ["hedonic-reward", "homeostatic-regulation", "actor-critic"]
    result = await classify_feedback(
        client=real_anthropic_client,
        feedback=(
            "The Q-learning epsilon-greedy implementation has a divide-by-zero bug "
            "when no actions have been tried yet."
        ),
        paradigms=paradigms,
    )
    assert result.target == "builder"
    assert result.paradigm in paradigms
