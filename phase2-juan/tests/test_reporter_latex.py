from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from simlab.reporter import Reporter, _prepare_latex_body


def test_prepare_latex_body_strips_tool_wrappers_and_document_end():
    body = r"""
\section{Resultados}
Texto **importante**.
\end{document}
</antml:parameter>
</invoke>
"""

    out = _prepare_latex_body(body)

    assert "importante" in out
    assert r"\end{document}" not in out
    assert "antml:parameter" not in out
    assert "</invoke>" not in out


def test_prepare_latex_body_does_not_convert_single_asterisk_math_to_italic():
    body = "La recompensa usa r * gamma y beta * delta sin crear cursiva."

    out = _prepare_latex_body(body)

    assert r"\textit" not in out
    assert "r * gamma" in out
    assert "beta * delta" in out


def test_prepare_latex_body_removes_malformed_tool_wrappers():
    body = r"""
\section{Conclusiones}
Texto final.
\end{antml:parameter>
</invoke>
"""

    out = _prepare_latex_body(body)

    assert "Texto final." in out
    assert "antml:parameter" not in out
    assert "</invoke>" not in out


def test_prepare_latex_body_removes_content_wrappers():
    body = r"\section{Fin}Texto.\end{content}"

    out = _prepare_latex_body(body)

    assert r"\end{content}" not in out
    assert "Texto." in out


def test_prepare_latex_body_escapes_unmatched_closing_braces_in_text():
    body = r"\section{Resultados}El valor Q((3, }here'), \texttt{move\_up}) subió."

    out = _prepare_latex_body(body)

    assert r"Q((3, \}here')" in out
    assert "move\\_up" in out


def test_prepare_latex_body_converts_tagged_display_math_to_equation():
    body = r"$$D(x) = \phi \cdot (x - s)^2 \tag{1}$$"

    out = _prepare_latex_body(body)

    assert r"\begin{equation}" in out
    assert r"\tag{1}" in out
    assert "$$" not in out


def test_prepare_latex_body_strips_unbalanced_text_commands():
    body = r"\textit{\texttt{\texttt{Hazlo todo: genera informe''}."

    out = _prepare_latex_body(body)

    assert r"\textit{" not in out
    assert r"\texttt{" not in out
    assert "Hazlo todo: genera informe" in out


def test_prepare_latex_body_wraps_table_rows_starting_with_brackets():
    body = "[4, 'here'] & stay & -14.83 & 2 \\\\"

    out = _prepare_latex_body(body)

    assert "{[4, 'here']} & stay" in out


@pytest.mark.asyncio
async def test_reporter_does_not_claim_pdf_when_llm_skips_compile():
    storage = AsyncMock()
    db = MagicMock()
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="No PDF generated")],
    )

    with (
        patch("simlab.reporter.run_agent_loop", new=AsyncMock(return_value=response)),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        out = await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": []}',
            run_id="run-1",
            experiment_id="exp-1",
        )

    assert out == "No PDF generated"
    assert reporter.last_pdf_key is None
    storage.put.assert_not_called()


@pytest.mark.asyncio
async def test_reporter_timeout_does_not_upload_fake_pdf():
    storage = AsyncMock()
    db = MagicMock()

    async def slow_loop(**kwargs):
        await __import__("asyncio").sleep(1)

    with (
        patch("simlab.reporter.REPORTER_LLM_TIMEOUT_SECONDS", 0.01),
        patch("simlab.reporter.run_agent_loop", side_effect=slow_loop),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        out = await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": []}',
            run_id="run-1",
            experiment_id="exp-timeout",
        )

    assert "tardó demasiado" in out
    assert reporter.last_pdf_key is None
    storage.put.assert_not_called()


@pytest.mark.asyncio
async def test_compile_report_uses_standard_pdf_fallback_when_tectonic_unavailable():
    storage = AsyncMock()
    db = MagicMock()
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[
            SimpleNamespace(
                type="text",
                text="No he podido compilar el informe PDF.",
            )
        ],
    )

    async def fake_loop(**kwargs):
        await kwargs["registry"]["compile_report"](
            {
                "content": r"\section{Resultados}Contenido real.",
                "filename": "informe_final",
            }
        )
        return response

    with (
        patch("simlab.reporter.run_agent_loop", side_effect=fake_loop),
        patch("simlab.reporter.subprocess.run", side_effect=FileNotFoundError()),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": []}',
            run_id="run-1",
            experiment_id="exp-no-tectonic",
        )

    assert reporter.last_pdf_key == "experiments/exp-no-tectonic/informe_final.pdf"
    pdf_upload = storage.put.await_args_list[1].args
    assert pdf_upload[0] == "experiments/exp-no-tectonic/informe_final.pdf"
    assert pdf_upload[1].startswith(b"%PDF")
    assert pdf_upload[2] == "application/pdf"


@pytest.mark.asyncio
async def test_compile_report_uses_standard_pdf_fallback_when_latex_fails():
    storage = AsyncMock()
    db = MagicMock()
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="Informe generado.")],
    )

    async def fake_loop(**kwargs):
        result = await kwargs["registry"]["compile_report"](
            {
                "content": r"\section{Resultados}\unknowncommand",
                "filename": "informe_con_error",
            }
        )
        assert '"fallback": "standard"' in result
        return response

    failed_compile = SimpleNamespace(
        returncode=1,
        stderr="! Undefined control sequence\nerror: halted",
    )

    with (
        patch("simlab.reporter.run_agent_loop", side_effect=fake_loop),
        patch("simlab.reporter.subprocess.run", return_value=failed_compile),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": []}',
            run_id="run-1",
            experiment_id="exp-latex-error",
        )

    assert reporter.last_pdf_key == "experiments/exp-latex-error/informe_con_error.pdf"
    pdf_upload = storage.put.await_args_list[1].args
    assert pdf_upload[1].startswith(b"%PDF")
