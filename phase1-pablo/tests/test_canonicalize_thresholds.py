"""Per-label thresholds — Paradigm gets a τ_direct/τ_loose pair, others
get τ_direct only."""

from decisionlab.canonicalize import LABEL_THRESHOLDS, threshold_for


def test_label_thresholds_keys():
    assert set(LABEL_THRESHOLDS.keys()) == {"Paradigm", "Variable", "Postulate"}


def test_threshold_for_paradigm_returns_pair():
    direct, loose = threshold_for("Paradigm")
    assert 0.7 <= loose <= direct <= 0.95


def test_threshold_for_variable_pair_equal():
    direct, loose = threshold_for("Variable")
    assert direct == loose  # no ancestor expansion for non-Paradigm labels


def test_threshold_for_postulate_pair_equal():
    direct, loose = threshold_for("Postulate")
    assert direct == loose


def test_threshold_for_unknown_label_falls_back():
    """Unknown labels get a sane default rather than raising."""
    direct, loose = threshold_for("Nonexistent")
    assert direct == 0.85  # legacy default
    assert loose == direct
