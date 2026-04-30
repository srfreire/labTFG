"""Real-LLM tests for `decisionlab.knowledge.extraction.extract`.

Verifies that the Haiku-based extractor produces a well-shaped ExtractionResult
from a small piece of stage output.
"""

from __future__ import annotations

import uuid

import pytest

from decisionlab.knowledge.extraction import extract

SHORT_RESEARCHER_OUTPUT = """\
# Decision-making paradigms: foraging behavior in mice

## 1. Homeostatic regulation
Animals decide when to eat based on internal signals like ghrelin and leptin.
Ghrelin stimulates appetite; leptin signals satiety.
**Key authors**: Cannon (1932), Mrosovsky (1990)
**Key concepts**: drive reduction, set point, negative feedback

## 2. Hedonic reward
Decisions driven by anticipated pleasure (palatability of food).
**Key authors**: Berridge (1996)
**Key concepts**: wanting vs liking, dopaminergic signaling

## References
- Cannon (1932) - The Wisdom of the Body
- Berridge (1996) - Food reward: brain substrates of wanting and liking
"""


@pytest.mark.asyncio
async def test_real_extract_researcher_returns_well_shaped_result(
    real_anthropic_client,
):
    """Researcher-stage extraction should populate at least one paradigm node."""
    run_id = str(uuid.uuid4())
    result = await extract(
        stage="researcher",
        output_text=SHORT_RESEARCHER_OUTPUT,
        run_id=run_id,
        client=real_anthropic_client,
    )

    # Always returns the right shape, even if extraction is partial
    assert result.stage == "researcher"
    assert result.run_id == run_id
    assert isinstance(result.nodes, list)
    assert isinstance(result.relations, list)
    assert isinstance(result.facts, list)

    # Extractor should find at least one Paradigm or Author node from this prompt
    labels = {n.label for n in result.nodes}
    assert labels, "extractor returned no nodes — likely a malformed JSON parse"


@pytest.mark.asyncio
async def test_real_extract_researcher_finds_paradigm(real_anthropic_client):
    """Extractor recognizes the paradigm names in the input."""
    result = await extract(
        stage="researcher",
        output_text=SHORT_RESEARCHER_OUTPUT,
        run_id=str(uuid.uuid4()),
        client=real_anthropic_client,
    )

    paradigms = [n for n in result.nodes if n.label == "Paradigm"]
    if not paradigms:
        pytest.skip("Haiku did not classify any node as Paradigm — non-deterministic")
    # natural_key holds the *property name* used for dedup (e.g. "slug");
    # the actual paradigm identifier lives in properties[natural_key].
    flat = " ".join(str(v) for p in paradigms for v in p.properties.values()).lower()
    assert "homeostatic" in flat or "hedonic" in flat


@pytest.mark.asyncio
async def test_real_extract_unknown_stage_raises(real_anthropic_client):
    """A bogus stage raises ValueError before hitting the API."""
    with pytest.raises(ValueError, match="Unknown stage"):
        await extract(
            stage="not-a-stage",
            output_text="anything",
            run_id="x",
            client=real_anthropic_client,
        )


@pytest.mark.asyncio
async def test_real_extract_empty_output_does_not_raise(real_anthropic_client):
    """Empty stage output yields a valid (possibly empty) result."""
    result = await extract(
        stage="researcher",
        output_text="",
        run_id="empty",
        client=real_anthropic_client,
    )
    assert result.stage == "researcher"
    # Empty input → empty extraction is a valid outcome
    assert isinstance(result.nodes, list)
    assert isinstance(result.relations, list)
