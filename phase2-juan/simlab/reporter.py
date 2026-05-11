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

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from simlab.loop import Registry, run_agent_loop
from simlab.utils import extract_text

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
    # *italic* → \textit{italic}
    content = re.sub(r"\*(.+?)\*", r"\\textit{\1}", content)
    # `code` → \texttt{code}
    content = re.sub(r"`([^`]+)`", r"\\texttt{\1}", content)
    return content


DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

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
Then ALSO call read_research with "deep/<paradigm-slug>.md" AND "formulations/<paradigm-slug>.md" \
for each paradigm used in the simulation. These files contain the full Phase 1 research \
(postulates, assumptions, variables, mathematical formulations) that MUST appear in the report.
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

    async def run(
        self,
        prompt: str,
        tracker_output: str,
        analyst_output: str,
        *,
        run_id: str,
        experiment_id: str,
        max_iterations: int = 8,
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

            content = _fix_markdown_in_latex(params["content"])
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

            # Download chart PNGs from S3 to temp dir for \includegraphics
            charts_prefix = f"experiments/{experiment_id}/charts/"
            chart_keys = await storage.list(charts_prefix)
            for ck in chart_keys:
                png_data = await storage.get(ck)
                local_name = ck.split("/")[-1]
                (Path(tmp) / local_name).write_bytes(png_data)

            try:
                result = subprocess.run(
                    ["tectonic", str(tex_path)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=tmp,
                )
                if result.returncode != 0:
                    error_lines = [
                        line
                        for line in result.stderr.split("\n")
                        if "error" in line.lower()
                    ]
                    shutil.rmtree(tmp, ignore_errors=True)
                    return json.dumps(
                        {
                            "success": False,
                            "errors": error_lines[:10]
                            if error_lines
                            else [result.stderr[-500:]],
                        }
                    )

                tex_key = f"experiments/{experiment_id}/report.tex"
                pdf_key = f"experiments/{experiment_id}/{safe_name}.pdf"
                tex_bytes = full_latex.encode()
                pdf_bytes = pdf_path.read_bytes()
                await storage.put(tex_key, tex_bytes, "text/x-tex")
                await storage.put(pdf_key, pdf_bytes, "application/pdf")
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
                    content_type="application/pdf",
                    db=db,
                )

                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps({"success": True, "pdf_path": pdf_key})
            except FileNotFoundError:
                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps(
                    {"success": False, "errors": ["'tectonic' not installed"]}
                )
            except subprocess.TimeoutExpired:
                shutil.rmtree(tmp, ignore_errors=True)
                return json.dumps(
                    {"success": False, "errors": ["Compilation timed out"]}
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
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=system,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            registry=registry,
            max_iterations=max_iterations,
            max_tokens=16384,
            on_tool_call=on_tool_call,
        )
        return extract_text(response)
