"""
Reporter agent — generates LaTeX reports and compiles them to PDF.

Flow:
  1. Reads Phase 1 research files for scientific context
  2. Combines Tracker observations + Analyst findings
  3. Generates LaTeX body content (sections, tables, lists)
  4. Compiles to PDF using tectonic
  5. Returns the path to the generated PDF
"""

from __future__ import annotations

import asyncio
from io import BytesIO
import json
import logging
import re
import subprocess
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from simlab.loop import Registry, run_agent_loop
from simlab.utils import extract_text


def _llm_latex_text(response) -> str:
    """Return the first text block from a Claude API response, unchanged.

    Unlike ``simlab.utils.extract_text`` this does NOT run the
    ``strip_markdown_fences`` JSON heuristic, which corrupts LaTeX by
    keeping only the substring between the first ``{`` and the last ``}``.
    Only fence stripping (``` blocks) is applied here.
    """
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text or not text.strip():
        raise RuntimeError(
            "LLM produced no text output "
            f"(stop_reason={getattr(response, 'stop_reason', None)})"
        )
    stripped = text.strip()
    match = re.match(
        r"^```(?:latex|tex)?\s*\n(.*?)\n```\s*$", stripped, re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return stripped

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from shared.database import DatabaseService
    from shared.storage import StorageService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fix_markdown_in_latex(content: str) -> str:
    """Convert Markdown remnants to valid LaTeX"""
    # **bold** → \textbf{bold}
    content = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", content)
    # `code` → \texttt{code}
    content = re.sub(r"`([^`]+)`", r"\\texttt{\1}", content)
    return content


def _prepare_latex_body(content: str) -> str:
    """Normalize LLM-produced report body before injecting it into the template."""
    content = _fix_markdown_in_latex(content)
    content = _flatten_text_commands(content)
    content = re.sub(r"(?m)^.*(?:antml:parameter|</?invoke\b).*$", "", content)
    content = re.sub(r"\\(?:begin|end)\{content\}", "", content)
    content = re.sub(
        r"\$\$(.*?\\tag\{[^{}]+\}.*?)\$\$",
        lambda match: "\\begin{equation}\n"
        + match.group(1).strip()
        + "\n\\end{equation}",
        content,
        flags=re.DOTALL,
    )
    content = _strip_unbalanced_text_commands(content)
    content = _wrap_table_rows_starting_with_brackets(content)
    content = _escape_unmatched_closing_braces(content)
    content = re.sub(r"\\begin\{document\}", "", content)
    content = re.sub(r"\\end\{document\}", "", content)
    return content.strip()


def _escape_unmatched_closing_braces(content: str) -> str:
    """Escape stray closing braces from raw model/debug text."""
    return "\n".join(
        _escape_unmatched_closing_braces_in_line(line)
        for line in content.splitlines()
    )


def _escape_unmatched_closing_braces_in_line(content: str) -> str:
    balance = 0
    output: list[str] = []
    for index, char in enumerate(content):
        if char == "{":
            balance += 1
            output.append(char)
        elif char == "}":
            if index > 0 and content[index - 1] == "\\":
                output.append(char)
            elif balance > 0:
                balance -= 1
                output.append(char)
            else:
                output.append(r"\}")
        else:
            output.append(char)
    return "".join(output)


def _strip_unbalanced_text_commands(content: str) -> str:
    """Drop fragile inline styling on lines whose braces are already broken."""
    fixed_lines = []
    for line in content.splitlines():
        brace_delta = _unescaped_brace_delta(line)
        if (
            re.search(r"\\text(?:bf|it|tt)\{", line)
            and brace_delta > 0
        ):
            line = re.sub(r"\\text(?:bf|it|tt)\{", "", line)
        fixed_lines.append(line)
    return "\n".join(fixed_lines)


def _flatten_text_commands(content: str) -> str:
    """Preserve text while removing fragile inline LaTeX styling commands."""
    previous = None
    while previous != content:
        previous = content
        content = re.sub(r"\\text(?:bf|it|tt)\{([^{}]*)\}", r"\1", content)
    return re.sub(r"\\text(?:bf|it|tt)\{", "", content)


def _wrap_table_rows_starting_with_brackets(content: str) -> str:
    def replace(match: re.Match[str]) -> str:
        indent, cell = match.groups()
        return f"{indent}{{{cell}}} &"

    return re.sub(r"(?m)^(\s*)(\[[^\n&]+])\s*&", replace, content)


def _unescaped_brace_delta(text: str) -> int:
    delta = 0
    for index, char in enumerate(text):
        if index > 0 and text[index - 1] == "\\":
            continue
        if char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _latex_body_to_plain_text(content: str) -> str:
    """Best-effort text extraction for the standard PDF fallback."""
    text = content
    text = re.sub(r"\\(?:sub)*section\*?\{([^{}]*)\}", r"\n\n\1\n", text)
    text = re.sub(r"\\(?:textbf|textit|texttt)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^{}]*\}", "", text)
    text = re.sub(r"\\(?:begin|end)\{[^{}]*\}", "\n", text)
    text = re.sub(r"\\\\", "\n", text)
    text = re.sub(r"\\[a-zA-Z]+(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r"\1", text)
    text = text.replace(r"\_", "_").replace(r"\%", "%").replace(r"\&", "&")
    text = re.sub(r"[{}$]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "Informe generado en formato estándar."


def _build_standard_pdf(content: str, title: str) -> bytes:
    """Render a simple local PDF when LaTeX compilation is unavailable."""
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    plain = _latex_body_to_plain_text(content)
    wrapped_lines: list[str] = []
    for paragraph in plain.splitlines():
        if not paragraph.strip():
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(paragraph, width=92) or [""])

    lines_per_page = 42
    pages = [
        wrapped_lines[i : i + lines_per_page]
        for i in range(0, len(wrapped_lines), lines_per_page)
    ] or [["Informe generado en formato estándar."]]

    buffer = BytesIO()
    with PdfPages(buffer) as pdf:
        for page_number, page_lines in enumerate(pages, start=1):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.08, 0.95, title, fontsize=16, weight="bold", va="top")
            fig.text(
                0.08,
                0.90,
                "\n".join(page_lines),
                fontsize=10,
                va="top",
                linespacing=1.35,
            )
            fig.text(0.92, 0.04, str(page_number), fontsize=9, ha="right")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
    return buffer.getvalue()


def _loads_json_object(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _build_standard_report_text(
    *,
    reason: str,
    prompt: str,
    tracker_output: str,
    analyst_output: str,
) -> str:
    """Build a readable standard report instead of dumping raw JSON."""
    tracker = _loads_json_object(tracker_output)
    analyst = _loads_json_object(analyst_output)
    sections = [
        "Aviso de generación",
        (
            "El Reporter no completó el informe LaTeX detallado "
            f"({reason}). Este PDF estándar conserva los hallazgos principales "
            "en formato legible."
        ),
        "Solicitud",
        prompt,
    ]

    summary = tracker.get("summary")
    if summary:
        sections.extend(["Resumen del experimento", str(summary)])

    trajectories = tracker.get("trajectories")
    if isinstance(trajectories, dict) and trajectories:
        lines = []
        for agent, data in trajectories.items():
            if not isinstance(data, dict):
                continue
            actions = data.get("actions") if isinstance(data.get("actions"), dict) else {}
            action_text = ", ".join(f"{k}: {v}" for k, v in actions.items())
            lines.append(
                f"- {agent}: {data.get('steps_survived', 'n/d')} pasos, "
                f"{data.get('resources_consumed', 'n/d')} recursos consumidos"
                + (f". Acciones: {action_text}." if action_text else ".")
            )
        if lines:
            sections.extend(["Trayectorias", "\n".join(lines)])

    episodes = tracker.get("episodes")
    if isinstance(episodes, list) and episodes:
        lines = []
        for ep in episodes[:8]:
            if not isinstance(ep, dict):
                continue
            label = ep.get("type", "episodio")
            step = ep.get("step") or ep.get("steps")
            step_text = f" paso(s) {step}" if step is not None else ""
            lines.append(f"- {label}{step_text}: {ep.get('description', '')}")
        sections.extend(["Episodios clave", "\n".join(lines)])

    patterns = analyst.get("patterns")
    if isinstance(patterns, list) and patterns:
        lines = []
        for pattern in patterns[:8]:
            if not isinstance(pattern, dict):
                continue
            pid = pattern.get("id", "Patrón")
            lines.append(f"- {pid}: {pattern.get('description', '')}")
            evidence = pattern.get("evidence")
            if evidence:
                lines.append(f"  Evidencia: {evidence}")
        sections.extend(["Patrones identificados", "\n".join(lines)])

    comparisons = analyst.get("comparisons")
    if isinstance(comparisons, list) and comparisons:
        lines = []
        for comp in comparisons[:6]:
            if not isinstance(comp, dict):
                continue
            metric = comp.get("metric", "comparación")
            lines.append(f"- {metric}: {comp.get('insight', '')}")
        sections.extend(["Comparaciones", "\n".join(lines)])

    if not tracker and tracker_output:
        sections.extend(["Observación del Tracker", tracker_output])
    if not analyst and analyst_output:
        sections.extend(["Hallazgos del Analyst", analyst_output])

    return "\n\n".join(section for section in sections if section)


DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_TOKENS = 4096
SECTION_MAX_TOKENS = 2500
# Sections run concurrently, so the wall-clock cost is roughly max(section_time)
# + tectonic compile. We still leave headroom for cold containers where tectonic
# has to download its LaTeX bundle on first run (~30-60s).
REPORTER_LLM_TIMEOUT_SECONDS = 240

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "report_template.tex"


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

READ_RESEARCH_TOOL = {
    "name": "read_research",
    "description": (
        "Read a research file from Phase 1. "
        "Available paths: 'report.md' (summary), 'deep/<paradigm>.md' (deep analysis), "
        "'formulations/<paradigm>.md' (math formulations). "
        "Paradigm slugs: homeostatic-regulation, hedonic-reward-based-regulation-of-food-intake, "
        "incentive-salience-theory, cognitive-executive-control-of-eating-behavior, "
        "associative-learning-and-conditioned-appetite, gut-brain-axis-signaling-in-food-intake-regulation, "
        "allostatic-opponent-process-model-of-food-intake."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path within the reports directory",
            },
        },
        "required": ["path"],
    },
}

COMPILE_REPORT_TOOL = {
    "name": "compile_report",
    "description": (
        "Compile a LaTeX report to PDF. Provide ONLY the LaTeX content for the body sections "
        "(everything between \\tableofcontents and \\end{document}). "
        "The cover page, preamble, and document structure are provided by the template. "
        "Use standard LaTeX: \\section{}, \\subsection{}, \\begin{itemize}, \\begin{tabular}, etc. "
        "Do NOT use \\begin{document} or \\end{document} — those are in the template. "
        "Choose a descriptive filename for the report (e.g. 'analisis_drive_reduction', 'comparativa_modelos')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "LaTeX body content (sections, text, tables — no preamble)",
            },
            "filename": {
                "type": "string",
                "description": "PDF filename without extension (e.g. 'analisis_drive_reduction'). "
                "Use lowercase, underscores, no spaces. Should describe the report content.",
            },
        },
        "required": ["content", "filename"],
    },
}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

REPORTER_SYSTEM_PROMPT = """\
You are the Reporter agent for a simulation laboratory. You generate professional \
LaTeX reports that integrate simulation results with scientific background.

You have 2 tools:
- read_research: read Phase 1 research files (state of the art, paradigm analyses, math formulations)
- compile_report: compile your LaTeX content into a PDF

## Process

1. Read the user's instructions carefully — they may ask for a SPECIFIC subset of data \
(e.g. only one agent, specific metrics, exclude certain sections, comparative focus). \
Tailor the report content accordingly.
2. Read the Tracker and Analyst data provided in the user message. Also check for an \
"Interaction history" section — if present, use it for the "Interacción con el Orquestador" section
3. Call read_research with "report.md" for a general overview. \
Then call read_research with "deep/<paradigm-slug>.md" AND "formulations/<paradigm-slug>.md" \
only for paradigms used in the simulation. Use concise excerpts from those files; do not paste \
long background sections verbatim.
4. Write LaTeX content for the report body in a SINGLE compile_report call. \
Choose a descriptive filename that reflects the report content (e.g. "analisis_drive_reduction", \
"comparativa_modelos", "informe_agente_pi_control"). Use lowercase + underscores.
5. If compilation fails, fix the LaTeX errors and try ONCE more. If it fails again, return the error — do NOT keep retrying.
6. Return the path to the generated PDF

## Report structure

Write ONLY the body content (sections). The template already provides cover page, \
preamble, and document wrapper. Your content goes between \\tableofcontents and \\end{document}.

IMPORTANT: The sections below are the FULL report structure. If the user requests a focused \
or partial report (e.g. "only about agent X", "just results and analysis"), adapt the structure — \
include only the relevant sections and data. Not every report needs all sections.

Standard sections (include all for a complete report, subset for focused reports):

\\section{Introducción}
Brief context about the simulation laboratory and its purpose.

\\section{Estado del Arte}
This section MUST include substantial content from Phase 1 research — not a brief summary. \
Call read_research with "report.md" first. Then for EACH paradigm used in the simulation, \
call read_research with "deep/<paradigm-slug>.md" to get the full deep research. Include:
- Foundations: historical context, key authors (Bernard, Cannon, Turrigiano, Keramati, etc.)
- Core postulates of the paradigm (P1, P2, P3...)
- Key assumptions
- Identified variables and their roles
This is Phase 1's contribution to the TFG — it must be well represented. \
Use 1-2 pages for this section. Cite authors properly.

\\section{Modelo de Decisión}
For EACH model used in the simulation: call read_research with "formulations/<paradigm-slug>.md" \
to get the complete mathematical formulation. Include:
- The paradigm the model implements and its theoretical basis
- The mathematical equations (use LaTeX math: $E(t)$, $\\Delta Q$, etc.)
- Key parameters and their meaning
- The decide/update cycle: how the model maps perception to action
Extract the paradigm from agent IDs (e.g. "drive_reduction_rl" → "homeostatic-regulation"). \
This section connects Phase 1's theoretical work with Phase 2's simulation.

\\section{Configuración del Experimento}
Describe the environment setup: grid size, resources, actions, agents, and number of simulation steps.

\\section{Predicciones}
If "Pre-simulation predictions" data is provided, include this section. For each paradigm, list \
the scientific predictions from Phase 1 deep research and explain what behavior was expected in \
the specific environment being tested. Frame it as hypotheses: "Based on homeostatic regulation \
theory, we expect the agent to..." This section is critical — it establishes the scientific \
expectations BEFORE presenting results. If no predictions are provided, skip this section.

\\section{Interacción con el Orquestador}
If an "Interaction history" section is provided in the input data, use it to describe how the user \
interacted with the Orchestrator agent to arrive at this experiment. Write a structured narrative: \
what the user requested at each step, what decisions the Orchestrator made, which agents were invoked \
and why. This documents the experimental methodology — how the human-AI collaboration shaped the \
simulation. Use \\begin{enumerate} for the sequence of steps. Keep it concise (half a page max). \
If no interaction history is provided, skip this section entirely.

\\section{Resultados de la Simulación}
Present the Tracker observations: trajectories, episodes, key events. Use tables and itemized \
lists to present data clearly. If chart images are available, include them using \
\\includegraphics[width=\\textwidth]{chart_1.png} — use the FILENAME only (e.g. chart_1.png), \
not a full path. The chart PNGs are placed in the same directory as the .tex file during compilation. \
Use the filenames provided in the "Available chart images" section.

\\section{Análisis}
Present the Analyst findings: patterns, comparisons, metrics. Use tables for comparisons. \
Include relevant chart images that support the analysis. Each chart should have a caption \
(use \\begin{figure}[h] \\centering \\includegraphics[width=0.9\\textwidth]{path} \
\\caption{...} \\end{figure}).

\\section{Conclusiones}
Synthesize findings. If predictions were provided, explicitly contrast them with the actual \
results: which predictions were confirmed, which were refuted, and what explains the discrepancies. \
What do the results tell us about the decision-making paradigms? What improvements could be made?

## LaTeX rules

- Use \\section{} and \\subsection{} for structure
- Use \\begin{itemize} for bullet lists
- Use \\begin{tabular}{lll} with \\toprule, \\midrule, \\bottomrule for tables
- Escape special chars: \\%, \\&, \\_, \\#, \\$
- Use --- for em-dashes, -- for en-dashes
- Do NOT include \\begin{document}, \\end{document}, or any preamble
- Write in Spanish
- Be concise — aim for 3-5 pages total. Quality over quantity.
- Generate the LaTeX in a SINGLE compile_report call — do not split across multiple calls
- NEVER use \\textbf{} or \\textit{} inside section/subsection titles
- Avoid nested formatting commands — keep it simple
- If a character causes issues, remove it rather than trying to escape it

## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it \
as follows:

### References (meta)
Use the returned Paper nodes to build real citations in the report body. \
Format: \\textit{Title} (Author, Year). If a DOI is available, include it in \
the References section at the end. Do NOT fabricate citations — use only what \
was returned. If zero results were returned, fall back to generic references \
from read_research files.

### Formulations
Include the relevant equations in the "Modelo de Decisión" section using LaTeX \
math environments (\\begin{equation} or \\begin{align}). Reference them by \
number when discussing model behavior in the Análisis section. This gives the \
report mathematical grounding from the Knowledge Graph's validated formulation \
nodes, complementing what read_research provides.

If knowledge context is empty or absent, proceed with read_research as the sole \
source — do not mention knowledge context absence in the report.
"""


# ---------------------------------------------------------------------------
# Reporter class
# ---------------------------------------------------------------------------


class Reporter:
    def __init__(
        self,
        *,
        client,
        storage: StorageService,
        db: DatabaseService,
        model: str = DEFAULT_MODEL,
    ):
        self.client = client
        self.model = model
        self._storage = storage
        self._db = db
        # Set inside compile_report when a PDF is successfully written; the
        # Reporter's final LLM message is free-form text, so the orchestrator
        # cannot reliably parse pdf_path back out of it.
        self.last_pdf_key: str | None = None

    async def _compile_and_store_report(
        self,
        *,
        content: str,
        filename: str,
        experiment_id: str,
    ) -> tuple[str, str]:
        """Compile sanitized LaTeX body and store the resulting PDF.

        On compile failure, attempt a single LLM-driven repair pass before
        falling back to the matplotlib standard PDF. The repair is what
        rescues otherwise-decent reports from sporadic math/escape mistakes
        in the LLM output (e.g. "$ never closed", stray %, _ outside math).
        """
        import shutil
        import tempfile

        from shared.artifacts import register_artifact

        storage = self._storage
        db = self._db
        safe_name = (
            re.sub(r"[^a-z0-9_]", "_", filename.lower().strip()).strip("_")
            or "report"
        )
        content = _prepare_latex_body(content)

        template = _TEMPLATE_PATH.read_text()

        tmp = tempfile.mkdtemp(prefix="report_")
        tex_path = Path(tmp) / f"{safe_name}.tex"
        pdf_path = Path(tmp) / f"{safe_name}.pdf"

        tex_key = f"experiments/{experiment_id}/report.tex"
        pdf_key = f"experiments/{experiment_id}/{safe_name}.pdf"

        charts_prefix = f"experiments/{experiment_id}/charts/"
        chart_keys = await storage.list(charts_prefix)
        for ck in chart_keys:
            png_data = await storage.get(ck)
            local_name = ck.split("/")[-1]
            (Path(tmp) / local_name).write_bytes(png_data)

        latest_full_latex = template.replace("%% CONTENT_PLACEHOLDER %%", content)

        async def store_outputs(pdf_bytes: bytes, content_type: str) -> str:
            tex_bytes = latest_full_latex.encode()
            await storage.put(tex_key, tex_bytes, "text/x-tex")
            await storage.put(pdf_key, pdf_bytes, content_type)
            await register_artifact(
                tex_key,
                "tex",
                len(tex_bytes),
                experiment_id=experiment_id,
                content_type="text/x-tex",
                db=db,
            )
            await register_artifact(
                pdf_key,
                "pdf",
                len(pdf_bytes),
                experiment_id=experiment_id,
                content_type=content_type,
                db=db,
            )
            self.last_pdf_key = pdf_key
            return pdf_key

        def run_tectonic(body: str) -> subprocess.CompletedProcess:
            nonlocal latest_full_latex
            latest_full_latex = template.replace("%% CONTENT_PLACEHOLDER %%", body)
            tex_path.write_text(latest_full_latex)
            return subprocess.run(
                ["tectonic", str(tex_path)],
                capture_output=True,
                text=True,
                timeout=240,
                cwd=tmp,
            )

        try:
            result = run_tectonic(content)
            if result.returncode == 0:
                key = await store_outputs(pdf_path.read_bytes(), "application/pdf")
                shutil.rmtree(tmp, ignore_errors=True)
                return key, "latex"

            error_lines = [
                line for line in result.stderr.split("\n") if "error" in line.lower()
            ]
            logger.warning(
                "sectioned report compile failed: errors=%s; attempting LLM repair",
                error_lines[:5] or result.stderr[-300:],
            )

            repaired = await self._repair_latex(content, error_lines, tex_path)
            if repaired and repaired != content:
                result2 = run_tectonic(repaired)
                if result2.returncode == 0:
                    key = await store_outputs(
                        pdf_path.read_bytes(), "application/pdf"
                    )
                    shutil.rmtree(tmp, ignore_errors=True)
                    logger.info("LaTeX repair pass succeeded")
                    return key, "latex"
                logger.warning(
                    "repaired compile still failing: errors=%s",
                    [
                        line
                        for line in result2.stderr.split("\n")
                        if "error" in line.lower()
                    ][:5],
                )

            fallback_content = (
                "Aviso de compilación\n\n"
                "La compilación LaTeX detallada no se pudo completar. "
                "Este PDF usa un formato estándar con el contenido del informe.\n\n"
                + content
            )
            key = await store_outputs(
                _build_standard_pdf(fallback_content, f"DecisionLab - {safe_name}"),
                "application/pdf",
            )
            shutil.rmtree(tmp, ignore_errors=True)
            return key, "standard"
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            fallback_content = (
                "Aviso de compilación\n\n"
                f"No se pudo ejecutar Tectonic ({type(exc).__name__}). "
                "Este PDF usa un formato estándar con el contenido del informe.\n\n"
                + content
            )
            key = await store_outputs(
                _build_standard_pdf(fallback_content, f"DecisionLab - {safe_name}"),
                "application/pdf",
            )
            shutil.rmtree(tmp, ignore_errors=True)
            return key, "standard"

    async def _repair_latex(
        self,
        broken_body: str,
        error_lines: list[str],
        tex_path: Path,
    ) -> str | None:
        """Ask the LLM to fix LaTeX errors. Returns repaired body or None."""
        if not error_lines:
            return None

        context_snippet = ""
        try:
            line_nums = {
                int(m.group(1))
                for line in error_lines
                if (m := re.search(r":(\d+):", line))
            }
            if line_nums and tex_path.exists():
                lines = tex_path.read_text().splitlines()
                wanted: set[int] = set()
                for n in line_nums:
                    for ln in range(max(1, n - 3), min(len(lines), n + 3) + 1):
                        wanted.add(ln)
                context_snippet = "\n".join(
                    f"L{ln}: {lines[ln - 1]}" for ln in sorted(wanted)
                )
        except Exception:
            context_snippet = ""

        repair_prompt = (
            "El siguiente cuerpo LaTeX falló al compilar con tectonic. "
            "Devuelve EXACTAMENTE el mismo contenido pero con los errores corregidos. "
            "Mantén las mismas \\section{} y el mismo contenido textual; "
            "no añadas explicaciones, preamble, \\begin{document}, \\end{document} ni "
            "marcadores de fence (```).\n\n"
            "Errores reportados por tectonic:\n"
            + "\n".join(error_lines[:10])
            + (
                "\n\nContexto alrededor de las líneas con error:\n" + context_snippet
                if context_snippet
                else ""
            )
            + "\n\nReglas obligatorias para la corrección:\n"
            "- TODA expresión matemática debe ir entre $...$ (inline) o "
            "\\begin{equation}...\\end{equation} (display).\n"
            "- NO uses \\(...\\) ni $$...$$ (este template no los acepta).\n"
            "- Fuera de math, escapa: \\_  \\%  \\&  \\#  \\$.\n"
            "- _ y ^ solo aparecen dentro de math mode.\n"
            "- No uses \\cite{} \\ref{} \\label{} (no hay bibtex ni cross-refs).\n"
            "- Balancea todas las llaves { }.\n"
            "- Si hay \\includegraphics, usa solo el nombre del PNG (chart_1.png), "
            "sin ruta.\n\n"
            "LaTeX a corregir (entrega solo el cuerpo corregido):\n"
            + broken_body
        )
        try:
            response = await self.client.messages.create(
                model=self.model,
                system=(
                    "Eres un asistente de reparación de LaTeX. "
                    "Devuelves SOLO el cuerpo LaTeX corregido, sin explicaciones "
                    "ni bloques de código markdown."
                ),
                tools=[],
                messages=[{"role": "user", "content": repair_prompt}],
                max_tokens=8192,
            )
        except Exception as exc:
            logger.warning("LaTeX repair LLM call failed: %s", exc)
            return None

        fixed = _llm_latex_text(response)
        if not fixed:
            return None
        fixed = re.sub(r"^```(?:latex|tex)?\s*", "", fixed)
        fixed = re.sub(r"\s*```\s*$", "", fixed)
        return _prepare_latex_body(fixed)

    async def _generate_sectioned_report(
        self,
        *,
        prompt: str,
        tracker_output: str,
        analyst_output: str,
        experiment_id: str,
        user_message: str,
        charts: list[dict] | None,
        prompt_suffix: str,
    ) -> str:
        """Generate bounded LaTeX sections and compile one assembled report."""
        sections = [
            (
                "Resumen ejecutivo",
                "Resume objetivo, resultado principal, estado final y hallazgo critico.",
            ),
            (
                "Entorno y modelo",
                "Describe entorno, modelo usado, contrato de decision y variables relevantes.",
            ),
            (
                "Resultados de simulacion",
                "Explica metricas, trayectoria, energia, recompensas y eventos observados.",
            ),
            (
                "Analisis del comportamiento",
                "Interpreta patrones, Q-table o politica, y relacion con la teoria.",
            ),
            (
                "Conclusiones y recomendaciones",
                "Lista conclusiones accionables y siguientes experimentos recomendados.",
            ),
        ]

        chart_lines = []
        for chart in charts or []:
            if chart.get("image_path"):
                filename = chart["image_path"].split("/")[-1]
                title = chart.get("title", filename)
                chart_lines.append(
                    "\\begin{figure}[h]\n"
                    "\\centering\n"
                    f"\\includegraphics[width=0.9\\textwidth]{{{filename}}}\n"
                    f"\\caption{{{_prepare_latex_body(title)}}}\n"
                    "\\end{figure}"
                )

        section_system = (
            REPORTER_SYSTEM_PROMPT
            + prompt_suffix
            + "\n\nReturn ONLY LaTeX body for the requested section. "
            "Do not call tools. Do not include preamble, document, table of contents, "
            "or wrapper tags. Keep the section under 450 words."
        )
        compact_context = user_message[:12000]

        async def generate_section(title: str, instruction: str) -> str:
            section_prompt = (
                f"Write section: {title}\n"
                f"Instruction: {instruction}\n\n"
                f"User report request:\n{prompt}\n\n"
                f"Experiment context:\n{compact_context}"
            )
            response = await self.client.messages.create(
                model=self.model,
                system=section_system,
                tools=[],
                messages=[{"role": "user", "content": section_prompt}],
                max_tokens=SECTION_MAX_TOKENS,
                cache_control={"type": "ephemeral"},
            )
            if getattr(response, "stop_reason", None) == "max_tokens":
                logger.warning(
                    "Reporter section '%s' hit max_tokens; retrying with compact prompt",
                    title,
                )
                response = await self.client.messages.create(
                    model=self.model,
                    system=section_system,
                    tools=[],
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Write section: {title}\n"
                                "Retry the same section. Be concise and complete. "
                                "Use short paragraphs and bullet lists when useful.\n\n"
                                f"Instruction: {instruction}\n\n"
                                f"Tracker:\n{tracker_output[:5000]}\n\n"
                                f"Analyst:\n{analyst_output[:5000]}"
                            ),
                        }
                    ],
                    max_tokens=SECTION_MAX_TOKENS,
                    cache_control={"type": "ephemeral"},
                )
            body = _prepare_latex_body(_llm_latex_text(response))
            return f"\\section{{{title}}}\n\n{body}"

        # Run sections concurrently — they are independent, and sequential
        # execution blew past REPORTER_LLM_TIMEOUT_SECONDS in production.
        section_bodies = list(
            await asyncio.gather(
                *(generate_section(title, instruction) for title, instruction in sections)
            )
        )

        if chart_lines:
            section_bodies.append("\\section{Graficos}\n\n" + "\n\n".join(chart_lines))

        content = "\n\n".join(section_bodies)
        pdf_key, mode = await self._compile_and_store_report(
            content=content,
            filename="informe_final",
            experiment_id=experiment_id,
        )
        quality_note = (
            "LaTeX detallado por secciones"
            if mode == "latex"
            else "formato estándar por fallo de compilación LaTeX"
        )
        return (
            f"PDF generado: `{pdf_key}`\n\n"
            f"Modo: {quality_note}.\n\n"
            "El informe se generó por secciones para evitar agotar tokens."
        )

    async def run(
        self,
        prompt: str,
        tracker_output: str,
        analyst_output: str,
        *,
        run_id: str,
        experiment_id: str,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        on_tool_call=None,
        interaction_summary: str | None = None,
        predictions: dict[str, str] | None = None,
        charts: list[dict] | None = None,
        extra_tools: list[dict] | None = None,
        extra_registry: dict | None = None,
        prompt_suffix: str = "",
        knowledge_context: str = "",
    ) -> str:
        storage = self._storage
        db = self._db
        self.last_pdf_key = None
        # Hard cap on compile_report attempts — the system prompt asks the LLM
        # to try ONCE more on failure, but in practice the LLM keeps retrying
        # and burns through max_iterations (and tokens) without producing a PDF.
        _MAX_COMPILE_ATTEMPTS = 2
        compile_state = {"attempts": 0}

        async def read_research(params: dict) -> str:
            """Read a Phase 1 research file from S3 (path-traversal safe)."""
            path = params["path"]
            if ".." in path or path.startswith("/"):
                return json.dumps({"error": f"Invalid path: {path}"})
            key = f"research/{run_id}/{path}"
            if not await storage.exists(key):
                return json.dumps({"error": f"File not found: {path}"})
            return await storage.get_text(key)

        async def compile_report(params: dict) -> str:
            """Compile LaTeX content into a PDF using tectonic."""
            import shutil
            import tempfile

            from shared.artifacts import register_artifact

            compile_state["attempts"] += 1
            if compile_state["attempts"] > _MAX_COMPILE_ATTEMPTS:
                return json.dumps(
                    {
                        "success": False,
                        "errors": [
                            f"Hard cap reached ({_MAX_COMPILE_ATTEMPTS} compile attempts). "
                            "Stop calling compile_report and return a brief text summary instead."
                        ],
                    }
                )

            content = _prepare_latex_body(params["content"])
            raw_name = params.get("filename", "report") or "report"
            safe_name = (
                re.sub(r"[^a-z0-9_]", "_", raw_name.lower().strip()).strip("_")
                or "report"
            )

            if not _TEMPLATE_PATH.exists():
                return json.dumps(
                    {"success": False, "errors": ["LaTeX template not found"]}
                )

            template = _TEMPLATE_PATH.read_text()
            full_latex = template.replace("%% CONTENT_PLACEHOLDER %%", content)

            tmp = tempfile.mkdtemp(prefix="report_")
            tex_path = Path(tmp) / f"{safe_name}.tex"
            pdf_path = Path(tmp) / f"{safe_name}.pdf"
            tex_path.write_text(full_latex)

            async def store_outputs(
                pdf_bytes: bytes, *, content_type: str = "application/pdf"
            ) -> str:
                tex_key = f"experiments/{experiment_id}/report.tex"
                pdf_key = f"experiments/{experiment_id}/{safe_name}.pdf"
                tex_bytes = full_latex.encode()
                await storage.put(tex_key, tex_bytes, "text/x-tex")
                await storage.put(pdf_key, pdf_bytes, content_type)
                await register_artifact(
                    tex_key,
                    "tex",
                    len(tex_bytes),
                    experiment_id=experiment_id,
                    content_type="text/x-tex",
                    db=db,
                )
                await register_artifact(
                    pdf_key,
                    "pdf",
                    len(pdf_bytes),
                    experiment_id=experiment_id,
                    content_type=content_type,
                    db=db,
                )
                self.last_pdf_key = pdf_key
                return pdf_key

            # Download chart PNGs from S3 to temp dir for \includegraphics
            charts_prefix = f"experiments/{experiment_id}/charts/"
            chart_keys = await storage.list(charts_prefix)
            for ck in chart_keys:
                png_data = await storage.get(ck)
                local_name = ck.split("/")[-1]
                (Path(tmp) / local_name).write_bytes(png_data)

            async def store_standard_pdf(errors: list[str]) -> str:
                logger.warning(
                    "compile_report using standard PDF fallback "
                    "(attempt %d): %s",
                    compile_state["attempts"],
                    errors[:3],
                )
                fallback_content = (
                    "\\section{Aviso de compilación}\n"
                    "La compilación LaTeX detallada no se pudo completar. "
                    "Este PDF usa un formato estándar con el contenido del informe.\n\n"
                    + content
                )
                pdf_bytes = _build_standard_pdf(
                    fallback_content, f"DecisionLab - {safe_name}"
                )
                return await store_outputs(pdf_bytes)

            try:
                result = subprocess.run(
                    ["tectonic", str(tex_path)],
                    capture_output=True,
                    text=True,
                    timeout=240,
                    cwd=tmp,
                )
                if result.returncode != 0:
                    error_lines = [
                        line
                        for line in result.stderr.split("\n")
                        if "error" in line.lower()
                    ]
                    logger.warning(
                        "compile_report failed (attempt %d): tex saved at %s, errors=%s",
                        compile_state["attempts"],
                        tex_path,
                        error_lines[:5] or result.stderr[-300:],
                    )
                    # Keep tmp dir on failure so the .tex + tectonic stderr are
                    # available for post-mortem debugging.
                    if result.returncode != 0:
                        pdf_key = await store_standard_pdf(
                            error_lines[:10] if error_lines else [result.stderr[-500:]]
                        )
                        shutil.rmtree(tmp, ignore_errors=True)
                        return json.dumps(
                            {
                                "success": True,
                                "pdf_path": pdf_key,
                                "fallback": "standard",
                                "warnings": error_lines[:10]
                                if error_lines
                                else [result.stderr[-500:]],
                            }
                        )

                pdf_key = await store_outputs(pdf_path.read_bytes())

                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps({"success": True, "pdf_path": pdf_key})
            except FileNotFoundError:
                pdf_key = await store_standard_pdf(["'tectonic' not installed"])
                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps(
                    {
                        "success": True,
                        "pdf_path": pdf_key,
                        "fallback": "standard",
                        "warnings": ["'tectonic' not installed"],
                    }
                )
            except subprocess.TimeoutExpired:
                pdf_key = await store_standard_pdf(["Compilation timed out"])
                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps(
                    {
                        "success": True,
                        "pdf_path": pdf_key,
                        "fallback": "standard",
                        "warnings": ["Compilation timed out"],
                    }
                )

        tools: list[dict] = [READ_RESEARCH_TOOL, COMPILE_REPORT_TOOL]
        registry: Registry = {
            "read_research": read_research,
            "compile_report": compile_report,
        }

        # Knowledge Backbone tools (sim-recall / P1-003)
        tools += extra_tools or []
        registry.update(extra_registry or {})

        parts = [prompt]
        if knowledge_context:
            parts.append(knowledge_context)
        parts.append(f"## Tracker observation log\n\n{tracker_output}")
        parts.append(f"## Analyst findings\n\n{analyst_output}")
        user_message = "\n\n".join(parts)
        if predictions:
            user_message += (
                "\n\n## Pre-simulation predictions (from Phase 1 deep research)\n\n"
            )
            for paradigm, preds in predictions.items():
                user_message += f"### {paradigm}\n\n{preds}\n\n"
        if charts:
            user_message += "\n\n## Available chart images for the report\n\n"
            for chart in charts:
                if chart.get("image_path"):
                    # Extract just the filename from the S3 key for \includegraphics
                    filename = chart["image_path"].split("/")[-1]
                    user_message += f"- **{chart['title']}** → `{filename}`\n"
        if interaction_summary:
            user_message += f"\n\n## Interaction history (user ↔ orchestrator)\n\n{interaction_summary}"
        system = REPORTER_SYSTEM_PROMPT + prompt_suffix

        try:
            return await asyncio.wait_for(
                self._generate_sectioned_report(
                    prompt=prompt,
                    tracker_output=tracker_output,
                    analyst_output=analyst_output,
                    experiment_id=experiment_id,
                    user_message=user_message,
                    charts=charts,
                    prompt_suffix=prompt_suffix,
                ),
                timeout=REPORTER_LLM_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "Sectioned Reporter timed out after %d seconds; using fallback PDF",
                REPORTER_LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "Sectioned Reporter failed with %s: %s; falling back to legacy flow",
                type(exc).__name__,
                exc,
                exc_info=True,
            )

        async def store_deterministic_standard_pdf(reason: str) -> str:
            from shared.artifacts import register_artifact

            pdf_key = f"experiments/{experiment_id}/informe_estandar.pdf"
            fallback_content = _build_standard_report_text(
                reason=reason,
                prompt=prompt,
                tracker_output=tracker_output,
                analyst_output=analyst_output,
            )
            pdf_bytes = _build_standard_pdf(
                fallback_content, "DecisionLab - informe_estandar"
            )
            await storage.put(pdf_key, pdf_bytes, "application/pdf")
            await register_artifact(
                pdf_key,
                "pdf",
                len(pdf_bytes),
                experiment_id=experiment_id,
                content_type="application/pdf",
                db=db,
            )
            self.last_pdf_key = pdf_key
            return pdf_key

        try:
            response = await asyncio.wait_for(
                run_agent_loop(
                    client=self.client,
                    model=self.model,
                    system=system,
                    tools=tools,
                    messages=[{"role": "user", "content": user_message}],
                    registry=registry,
                    max_iterations=max_iterations,
                    max_tokens=DEFAULT_MAX_TOKENS,
                    on_tool_call=on_tool_call,
                ),
                timeout=REPORTER_LLM_TIMEOUT_SECONDS,
            )
            text = extract_text(response)
            if (
                not self.last_pdf_key
                and getattr(response, "stop_reason", None) == "max_tokens"
            ):
                pdf_key = await store_deterministic_standard_pdf(
                    "el modelo agotó el presupuesto de tokens"
                )
                text = (
                    f"{text}\n\nEl informe detallado agotó el presupuesto de "
                    f"tokens. PDF generado en formato estándar con los datos disponibles: "
                    f"`{pdf_key}`"
                )
        except TimeoutError:
            logger.warning(
                "Reporter LLM timed out after %d seconds without generating a PDF",
                REPORTER_LLM_TIMEOUT_SECONDS,
            )
            pdf_key = await store_deterministic_standard_pdf(
                "el modelo tardó demasiado"
            )
            text = (
                "El Reporter tardó demasiado en generar el informe enriquecido; "
                f"PDF generado en formato estándar con los datos disponibles: `{pdf_key}`"
            )
        if self.last_pdf_key and self.last_pdf_key not in text:
            text = f"{text}\n\nPDF generado: `{self.last_pdf_key}`"
        return text
