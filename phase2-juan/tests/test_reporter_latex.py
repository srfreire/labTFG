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

    assert r"\textbf{importante}" in out
    assert r"\end{document}" not in out
    assert "antml:parameter" not in out
    assert "</invoke>" not in out


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
async def test_compile_report_reports_failure_when_tectonic_unavailable():
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

    assert reporter.last_pdf_key is None
    storage.put.assert_not_called()
