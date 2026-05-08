"""When the LLM emits __NEW__ but slug_proposal is empty, the fallback
must NOT collapse to a literal "paradigm" (which would silently merge
unrelated paradigms in Neo4j). Use a deterministic sha1 of the
definition so two distinct paradigms with empty proposals stay
distinct."""

import pytest

from decisionlab.agents.researcher import _slug_from_proposal


def test_nonempty_proposal_runs_slugify():
    assert _slug_from_proposal("Reinforcement Learning") == "reinforcement-learning"


def test_empty_proposal_uses_definition_hash():
    s = _slug_from_proposal(
        "", definition="A model of value-based action selection ..."
    )
    assert s.startswith("unnamed-")
    assert len(s) >= len("unnamed-") + 6


def test_empty_proposal_distinct_for_distinct_definitions():
    a = _slug_from_proposal("", definition="Variational free-energy minimization")
    b = _slug_from_proposal("", definition="Drift-diffusion evidence accumulation")
    assert a != b


def test_empty_proposal_no_definition_raises():
    """If both proposal AND definition are empty, we have no idea what
    paradigm this is. Refuse rather than silently minting a colliding slug."""
    with pytest.raises(ValueError, match="empty"):
        _slug_from_proposal("", definition="")
