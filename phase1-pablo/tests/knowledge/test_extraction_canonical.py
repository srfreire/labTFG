"""P1-002: ``ParadigmSlug`` ``Literal[...]`` validation at extraction time.

Locks the slug-bearing property models to the canonical paradigm set so a
malformed slug raises ``ValidationError`` before reaching the KG. The
forced tool-use path in ``call_structured`` translates ``ValidationError``
into ``StructuredOutputError``, which surfaces in the trace instead of
silently planting a junk slug.

Covers AC1–AC4 of the issue. AC5 (existing positive cases still pass) is
covered by the updated fixtures in ``test_extraction.py``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decisionlab.knowledge.extraction import (
    _CANONICAL_SLUGS,
    _build_result,
    _ParadigmProps,
    _PostulateProps,
    _VariableProps,
)
from decisionlab.knowledge.prompts import _CANONICAL

# ---------------------------------------------------------------------------
# AC1: ``_CANONICAL_SLUGS`` is derived from ``_CANONICAL`` at module import
# and includes ``"__NEW__"``.
# ---------------------------------------------------------------------------


def test_canonical_slugs_includes_every_paradigm_and_new_escape():
    """AC1: the Literal source covers every shipped slug plus ``__NEW__``."""
    expected_slugs = {p["slug"] for p in _CANONICAL}
    assert expected_slugs <= set(_CANONICAL_SLUGS)
    assert "__NEW__" in _CANONICAL_SLUGS
    # Total length = canonical count + the single escape slot. Catches a
    # regression where someone double-appends ``__NEW__``.
    assert len(_CANONICAL_SLUGS) == len(_CANONICAL) + 1


def test_canonical_slugs_order_is_deterministic():
    """Order tracks the JSON file order so the Pydantic-generated JSON
    schema is byte-stable across processes (matters for prompt caching)."""
    expected = (*(p["slug"] for p in _CANONICAL), "__NEW__")
    assert expected == _CANONICAL_SLUGS


# ---------------------------------------------------------------------------
# AC2: Paradigm slug Literal — accepts canonical, rejects invented variants.
# ---------------------------------------------------------------------------


def test_paradigm_with_canonical_slug_validates():
    """AC2 (positive): a Paradigm with a canonical slug parses cleanly."""
    props = _ParadigmProps(
        slug="reinforcement-learning",
        name="Reinforcement learning",
        description="Action-value learning from reward feedback.",
    )
    assert props.slug == "reinforcement-learning"


def test_paradigm_with_underscore_slug_raises():
    """AC2 (negative): the underscore variant is the canonical failure mode
    described in the phase spec — Pydantic rejects it at parse time."""
    with pytest.raises(ValidationError):
        _ParadigmProps(slug="reinforcement_learning", name="RL")


def test_paradigm_with_invented_variant_slug_raises():
    """An invented sub-variant of an existing paradigm is rejected — the
    LLM is supposed to reuse the umbrella slug or emit ``__NEW__``."""
    with pytest.raises(ValidationError):
        _ParadigmProps(slug="q-learning", name="Q-learning")


def test_paradigm_with_new_escape_slug_validates():
    """``__NEW__`` is the LLM's escape hatch when no canonical fits — it
    must pass the Literal so P1-003's verify-merge router can take over."""
    props = _ParadigmProps(slug="__NEW__", name="Brand new theory")
    assert props.slug == "__NEW__"


@pytest.mark.parametrize(
    "slug",
    [
        "prospect-theory",
        "drift-diffusion-model",
        "free-energy-principle",
        "active-inference",
        "homeostatic-regulation",
        "optimal-foraging-theory",
    ],
)
def test_every_canonical_paradigm_slug_validates(slug):
    """Sanity: every shipped canonical entry passes the Literal — guards
    against a typo in ``canonical-paradigms.json`` versus the prompt."""
    _ParadigmProps(slug=slug, name="x")


# ---------------------------------------------------------------------------
# AC3: Variable.paradigm_slug — must be canonical or ``__NEW__``.
# ---------------------------------------------------------------------------


def test_variable_with_canonical_paradigm_slug_validates():
    """AC3 (positive): paradigm_slug from the canonical set parses."""
    props = _VariableProps(
        name="reward",
        paradigm_slug="reinforcement-learning",
        type="scalar",
    )
    assert props.paradigm_slug == "reinforcement-learning"


def test_variable_with_non_canonical_paradigm_slug_raises():
    """AC3 (negative): an off-canon paradigm_slug is rejected — keeps a
    Variable from being scoped to a paradigm that doesn't exist."""
    with pytest.raises(ValidationError):
        _VariableProps(name="reward", paradigm_slug="q-learning")


def test_variable_missing_paradigm_slug_raises():
    """``paradigm_slug`` is required so a Variable can never silently land
    in the orphan namespace — the LLM has to commit to a paradigm."""
    with pytest.raises(ValidationError):
        _VariableProps(name="reward")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# AC4: Postulate.id — regex + canonical-prefix check.
# ---------------------------------------------------------------------------


def test_postulate_with_well_formed_id_validates():
    """AC4 (positive): ``<canonical-slug>:P<num>`` parses cleanly."""
    props = _PostulateProps(
        id="reinforcement-learning:P1",
        statement="Agents learn from reward.",
        falsifiable=True,
        paradigm_slug="reinforcement-learning",
    )
    assert props.id == "reinforcement-learning:P1"


def test_postulate_id_without_prefix_raises():
    """Bare ``P1`` (no paradigm prefix) is rejected — would collide across
    paradigms when written to the KG."""
    with pytest.raises(ValidationError):
        _PostulateProps(
            id="P1",
            statement="x",
            falsifiable=True,
            paradigm_slug="reinforcement-learning",
        )


def test_postulate_id_with_non_canonical_prefix_raises():
    """A prefix outside the canonical set is rejected even if the suffix
    is well-formed — the prefix is what scopes the postulate."""
    with pytest.raises(ValidationError):
        _PostulateProps(
            id="q-learning:P1",
            statement="x",
            falsifiable=True,
            paradigm_slug="reinforcement-learning",
        )


def test_postulate_id_with_uppercase_prefix_raises():
    """Slugs are always lowercase kebab; ``Reinforcement-Learning:P1`` is
    rejected by the shape regex."""
    with pytest.raises(ValidationError):
        _PostulateProps(
            id="Reinforcement-Learning:P1",
            statement="x",
            falsifiable=True,
            paradigm_slug="reinforcement-learning",
        )


def test_postulate_id_with_non_numeric_suffix_raises():
    """Suffix must be ``P<digits>`` — ``P1a`` is rejected."""
    with pytest.raises(ValidationError):
        _PostulateProps(
            id="reinforcement-learning:P1a",
            statement="x",
            falsifiable=True,
            paradigm_slug="reinforcement-learning",
        )


def test_postulate_with_new_paradigm_prefix_validates():
    """A Postulate emitted alongside a ``__NEW__`` Paradigm parses — the
    verify-merge router (P1-003) canonicalizes the prefix later. Without
    this allowance, every brand-new paradigm extraction would fail loud."""
    props = _PostulateProps(
        id="__NEW__:P1",
        statement="x",
        falsifiable=True,
        paradigm_slug="__NEW__",
    )
    assert props.id == "__NEW__:P1"


# ---------------------------------------------------------------------------
# Per-node validation in ``_build_result`` — invalid slug-bearing nodes are
# dropped individually so one bad slug doesn't void an otherwise-valid batch.
# ---------------------------------------------------------------------------


def _bare(nodes):
    return {"nodes": nodes, "relations": [], "facts": []}


def test_build_result_drops_invalid_paradigm():
    """A Paradigm with a non-canonical slug is dropped, not raised."""
    data = _bare(
        [
            {
                "label": "Paradigm",
                "properties": {"slug": "fabricated_slug", "name": "x"},
                "natural_key": "slug",
            }
        ]
    )
    result = _build_result(data, stage="researcher", run_id="r1")
    assert result.nodes == []


def test_build_result_drops_invalid_variable():
    """A Variable with a non-canonical paradigm_slug is dropped."""
    data = _bare(
        [
            {
                "label": "Variable",
                "properties": {"name": "x", "paradigm_slug": "fabricated"},
                "natural_key": "name",
            }
        ]
    )
    result = _build_result(data, stage="researcher", run_id="r1")
    assert result.nodes == []


def test_build_result_drops_invalid_postulate():
    """A Postulate with a bad id is dropped."""
    data = _bare(
        [
            {
                "label": "Postulate",
                "properties": {
                    "id": "P1",
                    "statement": "x",
                    "falsifiable": True,
                    "paradigm_slug": "reinforcement-learning",
                },
                "natural_key": "id",
            }
        ]
    )
    result = _build_result(data, stage="researcher", run_id="r1")
    assert result.nodes == []


def test_build_result_keeps_non_slug_labels():
    """Labels without a typed sub-validator (Author, Paper, BrainRegion,
    Equation, Parameter, Formulation, Model) skip per-label validation
    and survive — the canonical-set guarantee only applies to slug fields."""
    data = _bare(
        [
            {
                "label": "Author",
                "properties": {"name": "Walter B. Cannon", "affiliation": "Harvard"},
                "natural_key": "name",
            }
        ]
    )
    result = _build_result(data, stage="researcher", run_id="r1")
    assert len(result.nodes) == 1
    assert result.nodes[0].properties["name"] == "Walter B. Cannon"


def test_build_result_keeps_valid_paradigm_drops_invalid_in_same_batch():
    """One bad slug in a list doesn't void the rest — the regression that
    motivated this rewrite (smoke 2026-05-09: 90+ valid nodes lost to one
    `memory-based-foraging` slug)."""
    data = _bare(
        [
            {
                "label": "Paradigm",
                "properties": {
                    "slug": "reinforcement-learning",
                    "name": "RL",
                    "description": ".",
                },
                "natural_key": "slug",
            },
            {
                "label": "Paradigm",
                "properties": {"slug": "fabricated", "name": "x"},
                "natural_key": "slug",
            },
            {
                "label": "Paradigm",
                "properties": {
                    "slug": "prospect-theory",
                    "name": "Prospect Theory",
                    "description": ".",
                },
                "natural_key": "slug",
            },
        ]
    )
    result = _build_result(data, stage="researcher", run_id="r1")
    assert len(result.nodes) == 2
    assert {n.properties["slug"] for n in result.nodes} == {
        "reinforcement-learning",
        "prospect-theory",
    }
