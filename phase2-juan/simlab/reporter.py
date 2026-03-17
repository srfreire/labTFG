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

from simlab.loop import run_agent_loop, Registry
from simlab.utils import extract_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fix_markdown_in_latex(content: str) -> str:
    """Convert Markdown remnants to valid LaTeX"""
    # **bold** → \textbf{bold}
    content = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', content)
    # *italic* → \textit{italic}
    content = re.sub(r'\*(.+?)\*', r'\\textit{\1}', content)
    # `code` → \texttt{code}
    content = re.sub(r'`([^`]+)`', r'\\texttt{\1}', content)
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


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def _build_tools(
    research_dir: Path,
    output_dir: Path,
) -> tuple[list[dict], Registry]:
    """Build tool schemas and implementations for the Reporter."""

    async def read_research(params: dict) -> str:
        """Read a Phase 1 research file (path-traversal safe)."""
        path = params["path"]
        resolved = (research_dir / path).resolve()
        if not resolved.is_relative_to(research_dir.resolve()):
            return json.dumps({"error": f"Path escapes research directory: {path}"})
        if not resolved.exists():
            return json.dumps({"error": f"File not found: {path}"})
        return resolved.read_text()

    async def compile_report(params: dict) -> str:
        """Compile LaTeX content into a PDF using tectonic."""
        content = _fix_markdown_in_latex(params["content"])

        if not _TEMPLATE_PATH.exists():
            return json.dumps({"success": False, "errors": [f"LaTeX template not found at {_TEMPLATE_PATH}"]})

        # Insert content into the template
        template = _TEMPLATE_PATH.read_text()
        full_latex = template.replace("%% CONTENT_PLACEHOLDER %%", content)

        # Write .tex and compile
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

1. Read the Tracker and Analyst data provided in the user message
2. Call read_research with "report.md" — this contains a complete summary of ALL paradigms. \
DO NOT read individual deep/<paradigm>.md files unless report.md is missing.
3. Write LaTeX content for the report body in a SINGLE compile_report call
4. If compilation fails, fix the LaTeX errors and try ONCE more. If it fails again, return the error — do NOT keep retrying.
5. Return the path to the generated PDF

## Report structure

Write ONLY the body content (sections). The template already provides cover page, \
preamble, and document wrapper. Your content goes between \\tableofcontents and \\end{document}.

Required sections:

\\section{Introducción}
Brief context about the simulation laboratory and its purpose.

\\section{Estado del Arte}
Summarize the relevant paradigms from Phase 1 research. Reference key authors and concepts. \
Focus on paradigms that are relevant to the simulation being reported.

\\section{Modelo de Decisión}
Describe the decision model(s) used by the agents. The Tracker and Analyst data include agent IDs \
that reference the model names (e.g. "agent_drive_reduction_rl_0"). Extract the paradigm from the \
agent ID or model state, then use read_research with "formulations/<paradigm-slug>.md" to get the \
mathematical formulation. Explain: which paradigm each model implements, its key parameters, \
and how it makes decisions (decide/update cycle).

\\section{Configuración del Experimento}
Describe the environment setup: grid size, resources, actions, agents, and number of simulation steps.

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
- NEVER use \\textbf{} or \\textit{} inside section/subsection titles
- Avoid nested formatting commands — keep it simple
- If a character causes issues, remove it rather than trying to escape it
"""


# ---------------------------------------------------------------------------
# Reporter class
# ---------------------------------------------------------------------------

class Reporter:

    def __init__(self, *, client, model: str = DEFAULT_MODEL):
        self.client = client
        self.model = model

    async def run(self, prompt: str, tracker_output: str, analyst_output: str, *, research_dir: Path, output_dir: Path, max_iterations: int = 8) -> str:
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
