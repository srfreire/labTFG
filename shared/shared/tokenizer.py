"""Sparse tokenizer for BM25-equivalent retrieval in Qdrant.

This module is a shared utility used by multiple phases to produce sparse
vectors from plain text. Phase 1 originally shipped a copy at
`decisionlab.knowledge.tokenizer`; this shared version is the canonical one.
Phase 1 can migrate to import from here in a separate issue without
behavioural change — the hashing scheme is identical.
"""

from __future__ import annotations

import hashlib
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
    Indices: deterministic MD5-based hash of each token (stable across
    Python processes regardless of PYTHONHASHSEED).
    Values: raw term frequency (count of each token).
    """
    if not text:
        return [], []

    tokens = [t for t in _SPLIT_RE.split(text.lower()) if t and t not in STOPWORDS]

    if not tokens:
        return [], []

    freq: dict[int, float] = {}
    for token in tokens:
        digest = hashlib.md5(token.encode(), usedforsecurity=False).digest()
        idx = int.from_bytes(digest[:4], "little") & 0x7FFFFFFF
        freq[idx] = freq.get(idx, 0.0) + 1.0

    indices = sorted(freq.keys())
    values = [freq[i] for i in indices]
    return indices, values
