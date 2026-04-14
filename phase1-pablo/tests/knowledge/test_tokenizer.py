"""Tests for the sparse tokenizer utility."""

from __future__ import annotations

from decisionlab.knowledge.tokenizer import STOPWORDS, tokenize_to_sparse


def test_basic_tokenization():
    """Tokenize a simple phrase into indices + values."""
    indices, values = tokenize_to_sparse("hello world")
    assert len(indices) == 2
    assert len(values) == 2
    assert all(isinstance(i, int) for i in indices)
    assert all(isinstance(v, float) for v in values)


def test_lowercased():
    """Input is lowercased before tokenization."""
    i1, _ = tokenize_to_sparse("Hello")
    i2, _ = tokenize_to_sparse("hello")
    assert i1 == i2


def test_punctuation_split():
    """Punctuation is treated as a separator, not kept as a token."""
    indices, values = tokenize_to_sparse("Berridge, Robinson (1998)")
    # Should produce tokens: berridge, robinson, 1998
    assert len(indices) == 3


def test_stopwords_removed():
    """English stopwords are filtered out."""
    indices_with, _ = tokenize_to_sparse("the cat in the hat")
    indices_without, _ = tokenize_to_sparse("cat hat")
    # "the" and "in" are stopwords, so both should produce same tokens
    assert set(indices_with) == set(indices_without)


def test_term_frequency():
    """Repeated terms increase the corresponding value."""
    indices, values = tokenize_to_sparse("reward reward learning")
    # "reward" appears twice → its value should be 2.0
    idx_val = dict(zip(indices, values))
    reward_idx, _ = tokenize_to_sparse("reward")
    assert idx_val[reward_idx[0]] == 2.0


def test_empty_string():
    """Empty input returns empty lists."""
    indices, values = tokenize_to_sparse("")
    assert indices == []
    assert values == []


def test_all_stopwords():
    """Input of only stopwords returns empty lists."""
    indices, values = tokenize_to_sparse("the a an is are in on of")
    assert indices == []
    assert values == []


def test_consistency():
    """Same input always produces the same output."""
    r1 = tokenize_to_sparse("Q-learning convergence")
    r2 = tokenize_to_sparse("Q-learning convergence")
    assert r1 == r2


def test_stopwords_are_lowercase_english():
    """STOPWORDS contains expected common English words."""
    for word in (
        "the",
        "a",
        "an",
        "is",
        "are",
        "in",
        "on",
        "of",
        "for",
        "to",
        "and",
        "or",
        "with",
        "by",
        "from",
        "at",
    ):
        assert word in STOPWORDS
