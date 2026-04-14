"""Sparse tokenizer for BM25-equivalent retrieval in Qdrant.

Shared between indexing (P2-003) and query-time (P3-002) to ensure
consistent sparse representations.
"""

from __future__ import annotations

import re

STOPWORDS = frozenset(
    {
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
    }
)

_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def tokenize_to_sparse(text: str) -> tuple[list[int], list[float]]:
    """Convert text to a sparse vector (indices, values) for Qdrant.

    Tokenization: lowercase → split on non-alphanumeric → remove stopwords.
    Indices: deterministic hash of each token (Python's built-in hash masked
    to a positive 32-bit int).
    Values: raw term frequency (count of each token).
    """
    if not text:
        return [], []

    tokens = [t for t in _SPLIT_RE.split(text.lower()) if t and t not in STOPWORDS]

    if not tokens:
        return [], []

    freq: dict[int, float] = {}
    for token in tokens:
        idx = hash(token) & 0x7FFFFFFF
        freq[idx] = freq.get(idx, 0.0) + 1.0

    indices = sorted(freq.keys())
    values = [freq[i] for i in indices]
    return indices, values
