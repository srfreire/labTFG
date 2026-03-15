"""Reporter agent — generates LaTeX reports and compiles to PDF."""
from __future__ import annotations

import json
import subprocess
import logging
from pathlib import Path

from simlab.runtime import run_agent_loop, Registry
from simlab.utils import extract_text

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "report_template.tex"


# --- Tool schemas ---

READ_RESEARCH_TOOL = {
    "name": "read_research",
    "description": (
        "Read a research file from Phase 1 (Pablo's pipeline). "
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
            "path": {"type": "string", "description": "Relative path within the reports directory"},
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
        "Do NOT use \\begin{document} or \\end{document} — those are in the template."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "LaTeX body content (sections, text, tables — no preamble)",
            },
        },
        "required": ["content"],
    },
}


# --- Tool factories ---

def _build_tools(
    research_dir: Path,
    output_dir: Path,
) -> tuple[list[dict], Registry]:
    """Build tool schemas and registry for the Reporter."""

    async def read_research(params: dict) -> str:
        path = params["path"]
        resolved = (research_dir / path).resolve()
        if not resolved.is_relative_to(research_dir.resolve()):
            return json.dumps({"error": f"Path escapes research directory: {path}"})
        if not resolved.exists():
            return json.dumps({"error": f"File not found: {path}"})
        return resolved.read_text()

    async def compile_report(params: dict) -> str:
        content = params["content"]
        if not _TEMPLATE_PATH.exists():
            return json.dumps({"success": False, "errors": [f"LaTeX template not found at {_TEMPLATE_PATH}"]})

        template = _TEMPLATE_PATH.read_text()
        full_latex = template.replace("%% CONTENT_PLACEHOLDER %%", content)

        output_dir.mkdir(parents=True, exist_ok=True)
        tex_path = output_dir / "report.tex"
        pdf_path = output_dir / "report.pdf"
        tex_path.write_text(full_latex)

        try:
            result = subprocess.run(
                ["tectonic", str(tex_path)],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=output_dir,
            )
            if result.returncode != 0:
                error_lines = [l for l in result.stderr.split("\n") if "error" in l.lower()]
                return json.dumps({
                    "success": False,
                    "errors": error_lines[:10] if error_lines else result.stderr[-500:],
                })
            return json.dumps({"success": True, "pdf_path": str(pdf_path)})
        except FileNotFoundError:
            return json.dumps({"success": False, "errors": ["'tectonic' not installed. Run: brew install tectonic"]})
        except subprocess.TimeoutExpired:
            return json.dumps({"success": False, "errors": ["Compilation timed out after 120s"]})

    schemas = [READ_RESEARCH_TOOL, COMPILE_REPORT_TOOL]
    registry: Registry = {
        "read_research": read_research,
        "compile_report": compile_report,
    }
    return schemas, registry


# --- System prompt ---

REPORTER_SYSTEM_PROMPT = """\
You are the Reporter agent for a simulation laboratory. You generate professional \
LaTeX reports that integrate simulation results with scientific background.

You have 2 tools:
- read_research: read Phase 1 research files (state of the art, paradigm analyses, math formulations)
- compile_report: compile your LaTeX content into a PDF

## Process

1. Read the Tracker and Analyst data provided in the user message
2. Call read_research with "report.md" to get the state-of-the-art summary
3. Optionally read specific paradigm analyses from "deep/<paradigm>.md"
4. Write LaTeX content for the report body
5. Call compile_report with your content
6. If compilation fails, fix the LaTeX errors and try again
7. Return the path to the generated PDF

## Report structure

Write ONLY the body content (sections). The template already provides cover page, \
preamble, and document wrapper. Your content goes between \\tableofcontents and \\end{document}.

Required sections:

\\section{Introducción}
Brief context about the simulation laboratory and its purpose.

\\section{Estado del Arte}
Summarize the relevant paradigms from Phase 1 research. Reference key authors and concepts. \
Focus on paradigms that are relevant to the simulation being reported.

\\section{Configuración del Experimento}
Describe the environment setup: grid size, resources, actions, agents, and their decision models.

\\section{Resultados de la Simulación}
Present the Tracker observations: trajectories, episodes, key events. Use tables and itemized \
lists to present data clearly.

\\section{Análisis}
Present the Analyst findings: patterns, comparisons, metrics. Use tables for comparisons.

\\section{Conclusiones}
Synthesize findings. What do the results tell us about the decision-making paradigms? \
What improvements could be made?

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
"""


class Reporter:
    """Reporter agent — generates LaTeX reports compiled to PDF."""

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(
        self,
        prompt: str,
        tracker_output: str,
        analyst_output: str,
        *,
        research_dir: Path,
        output_dir: Path,
        max_iterations: int = 20,
    ) -> str:
        """Generate a PDF report. Returns the path to the PDF or an error message."""
        tools, registry = _build_tools(research_dir, output_dir)
        user_message = (
            f"{prompt}\n\n"
            f"## Tracker observation log\n\n{tracker_output}\n\n"
            f"## Analyst findings\n\n{analyst_output}"
        )
        response = await run_agent_loop(
            client=self.client,
            model=self.model,
            system=REPORTER_SYSTEM_PROMPT,
            tools=tools,
            messages=[{"role": "user", "content": user_message}],
            registry=registry,
            max_iterations=max_iterations,
            max_tokens=16384,
        )
        return extract_text(response)
