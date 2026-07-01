"""Unit tests for the Reporter faithfulness check (Layer 3 light)."""

from __future__ import annotations

from benchmark.faithfulness import Magnitude, check_report, is_fallback_report

MAGS = [
    Magnitude("comida", 42.0, ("comida", "consum")),
    Magnitude("pasos", 200.0, ("paso", "step")),
    Magnitude("recompensa", 42.0, ("recompensa", "reward")),
]


def test_faithful_report_scores_one():
    text = (
        "El agente consumió 42 unidades de comida a lo largo de 200 pasos, "
        "acumulando una recompensa total de 42."
    )
    rep = check_report(text, MAGS)
    assert rep.score == 1.0
    assert not rep.hallucinations


def test_hallucination_is_caught():
    text = (
        "El agente consumió 99 unidades de comida en 200 pasos, "
        "con una recompensa total de 42."
    )
    rep = check_report(text, MAGS)
    assert rep.score < 1.0
    caught = {r.key for r in rep.hallucinations}
    assert "comida" in caught
    assert "pasos" not in caught  # 200 is correct


def test_missing_magnitude_does_not_count_against_score():
    text = "El agente consumió 42 unidades de comida."  # no steps/reward mentioned
    rep = check_report(text, MAGS)
    statuses = {r.key: r.status for r in rep.results}
    assert statuses["comida"] == "faithful"
    assert statuses["pasos"] == "missing"
    assert statuses["recompensa"] == "missing"
    assert rep.score == 1.0  # only the mentioned, correct magnitude counts


def test_decimal_tolerance_with_spanish_separator():
    mags = [Magnitude("energia", 6.0, ("energía", "energia"))]
    text = "La energía final fue de 6,0 unidades."
    assert check_report(text, mags).score == 1.0


def test_close_but_off_value_is_hallucination():
    mags = [Magnitude("recompensa", 100.0, ("recompensa",))]
    text = "La recompensa total fue de 150."
    rep = check_report(text, mags)
    assert rep.results[0].status == "hallucinated"
    assert 150.0 in rep.results[0].claimed


def test_real_report_is_not_flagged_as_fallback():
    text = "Resultados de la simulación: el agente consumió 42 unidades de comida."
    assert not is_fallback_report(text)


def test_standard_pdf_fallback_banner_is_detected():
    text = (
        "Aviso de compilación. La compilación LaTeX detallada no se pudo "
        "completar. Este PDF usa un formato estándar con el contenido del informe."
    )
    assert is_fallback_report(text)
