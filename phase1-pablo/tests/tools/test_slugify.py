"""slugify must be idempotent and produce only [a-z0-9-] tokens."""

import re

import pytest

from decisionlab.tools.reports import slugify


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Reinforcement Learning", "reinforcement-learning"),
        ("Drift-diffusion model (DDM)", "drift-diffusion-model-ddm"),
        ("q_learning", "q-learning"),
        ("Q-Learning  ", "q-learning"),
        ("Bayesian   Inference", "bayesian-inference"),
        ("Naïve Bayes", "naive-bayes"),
        ("free-energy / variational", "free-energy-variational"),
        ("model: prospect theory", "model-prospect-theory"),
        ("---multiple---dashes---", "multiple-dashes"),
        ("a.b.c", "a-b-c"),
    ],
)
def test_slugify_canonical_forms(raw, expected):
    assert slugify(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "Reinforcement Learning",
        "Drift-diffusion model (DDM)",
        "Naïve Bayes",
        "model: prospect theory",
        "q_learning",
        "free-energy / variational",
    ],
)
def test_slugify_idempotent(raw):
    once = slugify(raw)
    twice = slugify(once)
    assert once == twice, f"slugify not idempotent: {once!r} -> {twice!r}"


def test_slugify_only_safe_chars():
    s = slugify("ÁÉÍÓÚáéíóú !@#$%^&*() Free Energy 2.0")
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s), f"unsafe chars in {s!r}"


def test_slugify_empty_input_returns_empty():
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("@@@") == ""
