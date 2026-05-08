"""Defense-in-depth: any slug-like natural key entering kg_writer
gets re-normalized through slugify. Catches LLM emissions that
bypassed the producer-side normalization."""

import pytest

from decisionlab.knowledge.kg_writer import _validate_natural_key


def test_slug_like_label_gets_renormalized():
    ok, value, err = _validate_natural_key(
        label="Paradigm", key_name="slug", key_value="Reinforcement Learning"
    )
    assert ok, err
    assert value == "reinforcement-learning"


def test_slug_already_canonical_passes_through():
    ok, value, err = _validate_natural_key(
        label="Paradigm", key_name="slug", key_value="prospect-theory"
    )
    assert ok
    assert value == "prospect-theory"


def test_uuid_shaped_slug_still_rejected():
    ok, value, err = _validate_natural_key(
        label="Paradigm",
        key_name="slug",
        key_value="a6744d26-4c5d-4e3f-9b8a-1f2c3d4e5f60",
    )
    assert not ok
    assert "uuid" in err.lower() or "natural key" in err.lower()


def test_non_slug_label_unchanged():
    """Author.name shouldn't be slugified — it's a human-readable name."""
    ok, value, err = _validate_natural_key(
        label="Author", key_name="name", key_value="Daniel Kahneman"
    )
    assert ok
    assert value == "Daniel Kahneman"


def test_oversized_slug_still_rejected():
    ok, value, err = _validate_natural_key(
        label="Paradigm",
        key_name="slug",
        key_value="x" * 200,
    )
    assert not ok


def test_normalize_to_empty_rejected():
    """Slug-like field with all non-alphanumerics — slugifies to empty.
    Refuse rather than write an empty key."""
    ok, value, err = _validate_natural_key(
        label="Paradigm", key_name="slug", key_value="@@@!!!"
    )
    assert not ok
    assert "empty" in err.lower()
