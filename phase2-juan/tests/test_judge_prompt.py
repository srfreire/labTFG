# phase2-juan/tests/test_judge_prompt.py
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "benchmark" / "JUDGE_PROMPT.md"


def test_prompt_has_placeholder_and_six_criteria():
    text = PROMPT.read_text().lower()
    assert "{bundle_dir}" in text
    for kw in ("entorno", "observación", "análisis", "informe", "robustez", "global"):
        assert kw in text, f"missing rubric criterion keyword: {kw}"
    assert "/100" in text
    assert "llm-judge.md" in text
