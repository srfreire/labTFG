from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from simlab.reporter import (
    Reporter,
    _build_standard_report_text,
    _env_facts_note,
    _prepare_latex_body,
    _render_env_section,
    _strip_section_scaffolding,
)


class _FakeMessages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        section_name = (
            kwargs["messages"][0]["content"]
            .splitlines()[0]
            .replace("Write section: ", "")
        )
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[
                SimpleNamespace(
                    type="text",
                    text=f"Contenido generado para {section_name}.",
                )
            ],
        )


class _RetryFakeMessages:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        section_name = (
            kwargs["messages"][0]["content"]
            .splitlines()[0]
            .replace("Write section: ", "")
        )
        if section_name == "Resumen ejecutivo" and len(self.calls) == 1:
            return SimpleNamespace(
                stop_reason="max_tokens",
                content=[
                    SimpleNamespace(
                        type="text",
                        text="Resumen parcial cortado por tokens.",
                    )
                ],
            )
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[
                SimpleNamespace(
                    type="text",
                    text=f"Contenido final para {section_name}.",
                )
            ],
        )


class _FakeClient:
    def __init__(self, messages=None):
        self.messages = messages or _FakeMessages()


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


def test_strip_section_scaffolding_drops_preamble_and_comment_lines():
    body = (
        "Basándome en el contexto, aquí está el contenido para Resumen ejecutivo:\n"
        "% Sección: Resultados de la Simulación\n"
        "El experimento comparó seis modelos en una rejilla 8x8.\n"
        "% LaTeX body content for Conclusiones section\n"
        "El modelo Wiener logró 10 consumos."
    )

    out = _strip_section_scaffolding(body)

    assert "Basándome en el contexto" not in out
    assert "% Sección" not in out
    assert "% LaTeX body content" not in out
    assert out.startswith("El experimento comparó seis modelos")
    assert "El modelo Wiener logró 10 consumos." in out


def test_strip_section_scaffolding_preserves_genuine_content():
    body = "El agente comió en el paso 5.\nLuego exploró el borde superior."

    assert _strip_section_scaffolding(body) == body


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


def test_prepare_latex_body_escapes_raw_underscores_in_text():
    # Model identifiers leak into captions/prose as raw snake_case, which
    # breaks tectonic with "Missing $ inserted" unless escaped.
    body = r"\caption{Evolución del drive (drive_reduction_rl)} y move_up."

    out = _prepare_latex_body(body)

    assert r"drive\_reduction\_rl" in out
    assert r"move\_up" in out
    assert "drive_reduction_rl" not in out.replace(r"\_", "")  # no raw _ left


def test_prepare_latex_body_preserves_underscores_inside_math():
    body = (
        r"La recompensa $R_t = -D(t)^2$ con $K_p$ y $Q(s_t, a_t)$ define la política."
    )

    out = _prepare_latex_body(body)

    assert "$R_t = -D(t)^2$" in out
    assert "$K_p$" in out
    assert "$Q(s_t, a_t)$" in out


def test_prepare_latex_body_preserves_underscores_in_includegraphics():
    body = r"\includegraphics[width=0.9\textwidth]{chart_2.png}"

    out = _prepare_latex_body(body)

    assert "{chart_2.png}" in out
    assert r"chart\_2.png" not in out


def test_prepare_latex_body_escapes_hash_and_percent_in_text():
    # Raw % silently eats the rest of the line (comment); raw # is an error.
    body = r"El 67% de las acciones y el agente #2 fracasaron."
    out = _prepare_latex_body(body)
    assert r"67\%" in out
    assert r"\#2" in out


def test_prepare_latex_body_preserves_specials_inside_math():
    body = r"La tasa $\alpha = 0.1$ y el 50% restante con $K_p$ activo."
    out = _prepare_latex_body(body)
    assert r"$\alpha = 0.1$" in out
    assert "$K_p$" in out
    assert r"50\%" in out


def test_render_env_section_is_deterministic_with_real_facts():
    facts = {
        "grid_w": 8,
        "grid_h": 8,
        "resources": [{"type": "food", "count": 6}],
        "actions": ["move_up", "move_down", "eat", "stay"],
        "steps": 30,
        "models": ["drive_reduction_rl", "pi_negative_feedback"],
        "seed": 42,
    }
    out = _render_env_section(facts)
    assert r"\section{Entorno y modelo}" in out
    # Facts come straight from the spec — never inferred by the LLM.
    assert r"8\times8" in out or "8x8" in out
    assert "30" in out
    assert "6" in out
    assert "drive_reduction_rl" in out
    assert "pi_negative_feedback" in out
    # No hallucinated grid size can appear because there is no LLM call.
    assert "5\\times5" not in out and "5x5" not in out


def test_render_env_section_skips_missing_fields():
    out = _render_env_section({"grid_w": 8, "grid_h": 8})
    assert r"\section{Entorno y modelo}" in out  # no crash on sparse facts


def test_env_facts_note_pins_authoritative_foraging_total():
    # Judge CASO2 caught "9 eventos de forrajeo" when trajectories sum to 7.
    # The note must hand the LLM the exact total so it stops summing by eye.
    facts = {
        "grid_w": 10,
        "grid_h": 10,
        "models": ["Continuo", "Q-learning", "Active-inf", "Jerárquico"],
        "consumption": {
            "Continuo": 4,
            "Q-learning": 2,
            "Active-inf": 1,
            "Jerárquico": 0,
        },
        "total_consumed": 7,
    }
    note = _env_facts_note(facts)
    assert "Total de consumos observados: 7" in note
    assert "Continuo: 4" in note and "Jerárquico: 0" in note
    # Judge CASO1 caught "10 de 15 recursos" (consumptions read as env resources)
    # and a miscount of zero-consumption models. The note must pin both — and the
    # zero-count is derived from the consumption dict itself (here: only
    # "Jerárquico" at 0), so it stays correct no matter who built env_facts.
    assert "NO el número de recursos del entorno" in note
    assert "Modelos con 0 consumos: exactamente 1 (Jerárquico)" in note


def test_env_facts_note_pins_per_model_action_distribution():
    # Judge CASO2 caught "46 movimientos antes del paso 24" and CASO1 attributed
    # a consumption to the wrong algebraic model. Handing the LLM the exact
    # per-model action counts removes the room to invent them.
    facts = {
        "grid_w": 8,
        "grid_h": 8,
        "actions_by_model": {
            "DDM (Wiener)": {"move_up": 12, "eat": 10, "move_left": 13},
            "Reponderación": {"move_right": 13, "stay": 1},
        },
    }
    note = _env_facts_note(facts)
    assert "Distribución de acciones por modelo" in note
    assert "DDM (Wiener): move_up=12, eat=10, move_left=13" in note
    assert "Reponderación: move_right=13, stay=1" in note


def test_strip_section_scaffolding_drops_english_generation_preamble():
    # Judge CASO1 flagged an "I'll write..." remnant leaking into the PDF.
    assert (
        _strip_section_scaffolding("I'll write the section.\nContenido real.")
        == "Contenido real."
    )
    assert (
        _strip_section_scaffolding("Let me provide the analysis.\nTexto.")
        == "Texto."
    )
    # Genuine Spanish prose starting mid-sentence is untouched.
    body = "El modelo Wiener consumió 10 recursos."
    assert _strip_section_scaffolding(body) == body


def test_strip_section_scaffolding_removes_embedded_sections_and_meta_paragraph():
    # Judge CASO2: an exec-summary body leaked "Según tus instrucciones, debo
    # escribir SOLO el contenido del body, sin incluir el heading ..." carrying
    # embedded \section{} commands that spawned a phantom "2." and a duplicated
    # "Resumen ejecutivo" in the table of contents.
    leak = (
        r"Este es un informe de sección única (\section{}). Según tus "
        r"instrucciones, debo escribir SOLO el contenido del body, sin incluir "
        r"el heading \section{Resumen ejecutivo} (que será añadido por el "
        r"orquestador)." + "\n\n---\n\nEste experimento compara cuatro modelos."
    )
    out = _strip_section_scaffolding(leak)
    assert "\\section" not in out
    assert "instrucciones" not in out.lower()
    assert out == "Este experimento compara cuatro modelos."
    # \subsection must survive — only top-level \section is stripped.
    sub = "\\subsection{Detalle}\nTexto real."
    assert "\\subsection{Detalle}" in _strip_section_scaffolding(sub)


def test_env_facts_note_omits_consumption_when_absent():
    # Production path (orchestrator) has no per-model consumption — the note must
    # degrade cleanly instead of emitting an empty or "None" foraging line.
    note = _env_facts_note({"grid_w": 8, "grid_h": 8, "total_consumed": None})
    assert "forrajeos exitosos" not in note.lower()
    assert "Rejilla: 8x8" in note


def test_render_env_section_drops_malformed_resources_instead_of_fabricating():
    facts = {
        "grid_w": 8,
        "grid_h": 8,
        "steps": 30,
        "resources": [{"type": "food"}, "bad", {"count": 5, "type": "water"}],
    }
    out = _render_env_section(facts)
    assert "5 recursos de tipo water" in out
    # malformed entries must not masquerade as facts in the authoritative section
    assert "?" not in out
    assert "de tipo recurso" not in out


def test_build_env_facts_from_real_state():
    from simlab.orchestrator import _build_env_facts

    state = {
        "spec": {
            "grid": {"width": 8, "height": 8},
            "resources": [{"type": "food", "count": 6}],
            "actions": [{"name": "eat"}, {"name": "stay"}],
        },
        "replay": {"grid_width": 8, "grid_height": 8, "total_steps": 30},
        "agent_to_model": {"a0": {"formulation": "drive_reduction_rl"}},
        "seed": 42,
    }
    facts = _build_env_facts(state)
    assert facts["grid_w"] == 8 and facts["grid_h"] == 8 and facts["steps"] == 30
    assert facts["models"] == ["drive_reduction_rl"]
    assert facts["actions"] == ["eat", "stay"]


def test_build_env_facts_populates_consumption_from_tracker_output():
    # Regression: _env_facts_note reads consumption/total_consumed, but
    # _build_env_facts never set them — the exact-total guidance was dead code
    # and the LLM invented "10 de 15 recursos" and miscounted zero-consumption
    # models. Pull the authoritative per-model counts from the Tracker output.
    import json

    from simlab.orchestrator import _build_env_facts

    state = {
        "spec": {"grid": {"width": 8, "height": 8}},
        "replay": {"grid_width": 8, "grid_height": 8, "total_steps": 60},
        "tracker_output": json.dumps(
            {
                "trajectories": {
                    "wiener": {"resources_consumed": 10},
                    "dualq": {"resources_consumed": 1},
                    "attr-rw": {"resources_consumed": 0},
                    "rescorla": {"resources_consumed": 0},
                }
            }
        ),
    }
    facts = _build_env_facts(state)
    assert facts["consumption"] == {
        "wiener": 10,
        "dualq": 1,
        "attr-rw": 0,
        "rescorla": 0,
    }
    assert facts["total_consumed"] == 11


def test_build_env_facts_tolerates_missing_or_malformed_tracker_output():
    from simlab.orchestrator import _build_env_facts

    base = {
        "spec": {"grid": {"width": 8, "height": 8}},
        "replay": {"grid_width": 8, "grid_height": 8, "total_steps": 60},
    }
    # No tracker output yet → no consumption keys, but facts still returned.
    facts = _build_env_facts(base)
    assert facts is not None and "total_consumed" not in facts
    # Malformed JSON must not crash the report path.
    facts = _build_env_facts({**base, "tracker_output": "{not json"})
    assert facts is not None and "total_consumed" not in facts


def test_build_env_facts_returns_none_when_core_facts_missing():
    from simlab.orchestrator import _build_env_facts

    assert _build_env_facts({"spec": {}, "replay": {}}) is None
    # grid present but no steps → still None (don't trust a partial section)
    assert _build_env_facts({"replay": {"grid_width": 8, "grid_height": 8}}) is None


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


def test_build_standard_report_text_formats_json_instead_of_dumping_it():
    tracker = """
{
  "summary": "Agente sobrevivió 50 pasos.",
  "trajectories": {
    "drive-reduction-rl": {
      "steps_survived": 50,
      "resources_consumed": 1,
      "actions": {"stay": 17, "eat": 1}
    }
  },
  "episodes": [
    {"type": "starvation", "step": 49, "description": "Colapso energético."}
  ]
}
"""
    analyst = """
{
  "patterns": [
    {"id": "P1", "description": "Fallo homeostático.", "evidence": "Drive subió."}
  ],
  "comparisons": [
    {"metric": "alimentación", "insight": "Eat casi nunca se ejecutó."}
  ]
}
"""

    text = _build_standard_report_text(
        reason="test",
        prompt="Informe comparativo",
        tracker_output=tracker,
        analyst_output=analyst,
    )

    assert "Trayectorias" in text
    assert "drive-reduction-rl: 50 pasos, 1 recursos consumidos" in text
    assert "Patrones identificados" in text
    assert "P1: Fallo homeostático." in text
    assert '"trajectories"' not in text
    assert '"patterns"' not in text


@pytest.mark.asyncio
async def test_reporter_generates_report_in_sections_without_legacy_loop():
    storage = AsyncMock()
    storage.list.return_value = []
    db = MagicMock()
    client = _FakeClient()

    def fake_compile(args, **kwargs):
        tex_path = Path(kwargs["cwd"]) / "informe_final.pdf"
        tex_path.write_bytes(b"%PDF sectioned")
        return SimpleNamespace(returncode=0, stderr="")

    with (
        patch("simlab.reporter.run_agent_loop", new=AsyncMock()) as legacy_loop,
        patch("simlab.reporter.subprocess.run", side_effect=fake_compile),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=client, storage=storage, db=db)
        out = await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": ["analyst"]}',
            run_id="run-1",
            experiment_id="exp-sectioned",
        )

    assert legacy_loop.await_count == 0
    assert len(client.messages.calls) == 5
    assert all(call["max_tokens"] == 2500 for call in client.messages.calls)
    assert reporter.last_pdf_key == "experiments/exp-sectioned/informe_final.pdf"
    assert "por secciones" in out
    pdf_upload = storage.put.await_args_list[1].args
    assert pdf_upload[0] == "experiments/exp-sectioned/informe_final.pdf"
    assert pdf_upload[1].startswith(b"%PDF")


@pytest.mark.asyncio
async def test_sectioned_compile_falls_back_to_llm_repair_then_succeeds():
    """If tectonic fails once, the Reporter asks the LLM to fix the LaTeX
    and re-compiles before falling back to the matplotlib standard PDF."""
    storage = AsyncMock()
    storage.list.return_value = []
    db = MagicMock()

    class _RepairClient:
        def __init__(self):
            self.messages = self
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            content = kwargs["messages"][0]["content"]
            # Section calls have "Write section:" prefix; repair has "falló al compilar"
            if "compilar" in content:
                text = r"\section{Resumen}Cuerpo reparado."
            else:
                text = r"\section{Resumen}Cuerpo $bad math"
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text=text)],
            )

    client = _RepairClient()
    compile_attempts = {"count": 0}

    def fake_compile(args, **kwargs):
        compile_attempts["count"] += 1
        tex_path = Path(kwargs["cwd"]) / "informe_final.tex"
        tex_text = tex_path.read_text() if tex_path.exists() else ""
        if compile_attempts["count"] == 1:
            return SimpleNamespace(
                returncode=1,
                stderr="error: informe_final.tex:50: Missing $ inserted\nerror: halted",
            )
        # Repair attempt succeeded
        pdf_path = Path(kwargs["cwd"]) / "informe_final.pdf"
        pdf_path.write_bytes(b"%PDF repaired ok")
        assert "reparado" in tex_text
        return SimpleNamespace(returncode=0, stderr="")

    with (
        patch("simlab.reporter.subprocess.run", side_effect=fake_compile),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=client, storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": ["analyst"]}',
            run_id="run-1",
            experiment_id="exp-repair",
        )

    # 5 sections + 1 repair = 6 LLM calls
    assert len(client.calls) == 6
    assert compile_attempts["count"] == 2
    assert reporter.last_pdf_key == "experiments/exp-repair/informe_final.pdf"
    pdf_upload = storage.put.await_args_list[1].args
    assert pdf_upload[1] == b"%PDF repaired ok"


@pytest.mark.asyncio
async def test_sectioned_compile_falls_back_to_standard_pdf_when_repair_also_fails():
    """When the LLM repair attempt still produces uncompilable LaTeX, we
    finally fall back to the matplotlib standard PDF."""
    storage = AsyncMock()
    storage.list.return_value = []
    db = MagicMock()

    class _BadRepairClient:
        def __init__(self):
            self.messages = self
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[
                    SimpleNamespace(
                        type="text",
                        text=r"\section{Resumen}Cuerpo $unbalanced.",
                    )
                ],
            )

    client = _BadRepairClient()

    def fake_compile(args, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stderr="error: informe_final.tex:50: Missing $ inserted",
        )

    with (
        patch("simlab.reporter.subprocess.run", side_effect=fake_compile),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=client, storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": ["analyst"]}',
            run_id="run-1",
            experiment_id="exp-repair-fails",
        )

    assert reporter.last_pdf_key == "experiments/exp-repair-fails/informe_final.pdf"
    # When repair also fails we now persist the broken tex for debugging, so
    # find the PDF upload by key instead of by index.
    pdf_uploads = [
        call.args
        for call in storage.put.await_args_list
        if call.args[0].endswith(".pdf")
    ]
    assert len(pdf_uploads) == 1
    assert pdf_uploads[0][0] == "experiments/exp-repair-fails/informe_final.pdf"
    assert pdf_uploads[0][1].startswith(b"%PDF")
    assert pdf_uploads[0][2] == "application/pdf"
    # The post-repair broken tex should have been uploaded
    tex_uploads = [
        call.args[0]
        for call in storage.put.await_args_list
        if call.args[0].endswith(".tex")
    ]
    assert any("broken_after_repair" in k for k in tex_uploads)


@pytest.mark.asyncio
async def test_reporter_retries_section_when_generation_hits_max_tokens():
    storage = AsyncMock()
    storage.list.return_value = []
    db = MagicMock()
    messages = _RetryFakeMessages()
    client = _FakeClient(messages)

    def fake_compile(args, **kwargs):
        pdf_path = Path(kwargs["cwd"]) / "informe_final.pdf"
        pdf_path.write_bytes(b"%PDF retried section")
        return SimpleNamespace(returncode=0, stderr="")

    with (
        patch("simlab.reporter.subprocess.run", side_effect=fake_compile),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=client, storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": ["analyst"]}',
            run_id="run-1",
            experiment_id="exp-section-retry",
        )

    assert len(messages.calls) == 6
    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert "Retry the same section" in retry_prompt
    assert all(call["max_tokens"] == 2500 for call in messages.calls)
    assert reporter.last_pdf_key == "experiments/exp-section-retry/informe_final.pdf"


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
async def test_reporter_timeout_uploads_standard_pdf_fallback():
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
    assert reporter.last_pdf_key == "experiments/exp-timeout/informe_estandar.pdf"
    pdf_upload = storage.put.await_args.args
    assert pdf_upload[0] == "experiments/exp-timeout/informe_estandar.pdf"
    assert pdf_upload[1].startswith(b"%PDF")
    assert "PDF generado" in out


@pytest.mark.asyncio
async def test_reporter_max_tokens_uploads_standard_pdf_fallback():
    storage = AsyncMock()
    db = MagicMock()
    response = SimpleNamespace(
        stop_reason="max_tokens",
        content=[SimpleNamespace(type="text", text="Informe parcial sin tool call")],
    )

    with (
        patch("simlab.reporter.run_agent_loop", new=AsyncMock(return_value=response)),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        out = await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": ["analyst"]}',
            run_id="run-1",
            experiment_id="exp-max-tokens",
        )

    assert reporter.last_pdf_key == "experiments/exp-max-tokens/informe_estandar.pdf"
    pdf_upload = storage.put.await_args.args
    assert pdf_upload[0] == "experiments/exp-max-tokens/informe_estandar.pdf"
    assert pdf_upload[1].startswith(b"%PDF")
    assert "PDF generado" in out


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


@pytest.mark.asyncio
async def test_compile_report_happy_path_produces_real_latex_pdf_not_fallback():
    """The success path must store the genuine tectonic PDF, not the standard
    fallback. This is the inverse of the fallback tests above: it guards against
    a regression where every report silently degrades to the matplotlib PDF."""
    storage = AsyncMock()
    storage.list = AsyncMock(return_value=[])
    db = MagicMock()
    real_pdf = b"%PDF-1.5\n% genuine tectonic output\n%%EOF\n"

    def fake_tectonic(cmd, **kwargs):
        # Emulate a successful compile: write the sibling .pdf and exit 0.
        tex_path = Path(cmd[1])
        tex_path.with_suffix(".pdf").write_bytes(real_pdf)
        return SimpleNamespace(returncode=0, stderr="")

    captured: dict[str, str] = {}
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="Informe generado.")],
    )

    async def fake_loop(**kwargs):
        captured["result"] = await kwargs["registry"]["compile_report"](
            {
                "content": r"\section{Resultados}Contenido válido del informe.",
                "filename": "informe_ok",
            }
        )
        return response

    with (
        patch("simlab.reporter.run_agent_loop", side_effect=fake_loop),
        patch("simlab.reporter.subprocess.run", side_effect=fake_tectonic),
        patch("shared.artifacts.register_artifact", new=AsyncMock()),
    ):
        reporter = Reporter(client=MagicMock(), storage=storage, db=db)
        await reporter.run(
            "genera informe",
            '{"summary": "tracker"}',
            '{"patterns": []}',
            run_id="run-1",
            experiment_id="exp-ok",
        )

    result = captured["result"]
    # The tool reports success WITHOUT the fallback marker.
    assert '"success": true' in result
    assert "fallback" not in result
    # The stored PDF is exactly tectonic's output — not the matplotlib fallback.
    pdf_upload = storage.put.await_args_list[1].args
    assert pdf_upload[0] == "experiments/exp-ok/informe_ok.pdf"
    assert pdf_upload[1] == real_pdf
    assert reporter.last_pdf_key == "experiments/exp-ok/informe_ok.pdf"
