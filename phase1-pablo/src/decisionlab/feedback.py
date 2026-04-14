"""Interactive feedback functions for each pipeline review stage.

Each function uses questionary for user input and rich for display.
All questionary calls are wrapped with ``asyncio.to_thread`` for async compat.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.markdown import Markdown

from decisionlab.parsing import filter_formulations_md, parse_formulation_headers

console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _ask(question: questionary.Question) -> Any:
    """Run a questionary prompt in a background thread."""
    return await asyncio.to_thread(question.unsafe_ask)


def _discover_paradigm_slugs(reports_dir: Path) -> list[str]:
    """Return sorted paradigm slugs from ``deep/*.md`` files."""
    deep_dir = reports_dir / "deep"
    if not deep_dir.is_dir():
        return []
    return sorted(p.stem for p in deep_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# REVIEW_RESEARCH
# ---------------------------------------------------------------------------

async def review_research(reports_dir: Path) -> tuple[list[str], str | None]:
    """Interactive review of research results.

    Returns ``(approved_paradigms, additional_paradigm_name_or_None)``.
    """
    slugs = _discover_paradigm_slugs(reports_dir)
    if not slugs:
        console.print("[bold red]No deep research reports found.[/bold red]")
        return [], None

    console.print()
    console.rule("[bold green]Review Research Results")
    console.print(f"Found {len(slugs)} paradigm(s) with deep reports.\n")

    approved: list[str] = await _ask(
        questionary.checkbox("Select paradigms to approve:", choices=slugs),
    )

    add_more: bool = await _ask(
        questionary.confirm("Investigate additional paradigms?", default=False),
    )

    additional: str | None = None
    if add_more:
        additional = await _ask(
            questionary.text("Paradigm name to investigate:"),
        )
        if not additional or not additional.strip():
            additional = None

    return approved, additional


# ---------------------------------------------------------------------------
# REVIEW_FORMALIZE
# ---------------------------------------------------------------------------

async def review_formalize(
    reports_dir: Path,
    paradigm_slugs: list[str],
    *,
    run_id: str = "",
) -> dict[str, list[int]]:
    """Double-level interactive selection of formalized paradigms/formulations.

    Returns ``{paradigm_slug: [1-based formulation numbers]}``.
    Also rewrites each selected paradigm's formulation file in S3 to keep
    only the chosen formulations.
    """
    import shared

    console.print()
    console.rule("[bold green]Review Formalization Results")

    # Level 1 — select paradigms
    approved_paradigms: list[str] = await _ask(
        questionary.checkbox("Select paradigms to keep:", choices=paradigm_slugs),
    )

    if not approved_paradigms:
        console.print("[yellow]No paradigms selected.[/yellow]")
        return {}

    selected_formulations: dict[str, list[int]] = {}

    for slug in approved_paradigms:
        s3_key = f"research/{run_id}/formulations/{slug}.md"
        try:
            text = await shared.storage.get_text(s3_key)
        except Exception:
            console.print(f"[yellow]Warning: {s3_key} not found, skipping.[/yellow]")
            continue

        headers = parse_formulation_headers(text)

        if not headers:
            console.print(f"[yellow]No formulation headers found in {slug}.md, keeping as-is.[/yellow]")
            selected_formulations[slug] = []
            continue

        # Level 2 — per-paradigm formulation selection
        choices = [
            questionary.Choice(
                title=f"Formulation {num}: {name}",
                value=num,
            )
            for num, name, _, _ in headers
        ]

        console.print(f"\n[bold cyan]{slug}[/bold cyan]")
        kept: list[int] = await _ask(
            questionary.checkbox(f"Select formulations to keep for '{slug}':", choices=choices),
        )

        selected_formulations[slug] = kept

        # Rewrite the formulation file in S3 to keep only selected formulations
        if kept:
            filtered = filter_formulations_md(text, kept)
            await shared.storage.put_text(s3_key, filtered)
            console.print(f"  [dim]Kept {len(kept)} formulation(s), rewrote {slug}.md[/dim]")
        else:
            console.print(f"  [yellow]No formulations selected for {slug}.[/yellow]")

    return selected_formulations


# ---------------------------------------------------------------------------
# GET_ENV_SPEC
# ---------------------------------------------------------------------------

async def get_env_spec() -> Path:
    """Prompt user for the path to ``env_spec.json`` and validate it."""
    console.print()
    console.rule("[bold green]Environment Specification")

    while True:
        raw: str = await _ask(
            questionary.path("Path to env_spec.json from Phase 2:"),
        )

        path = Path(raw).expanduser().resolve()

        if not path.exists():
            console.print(f"[bold red]File not found: {path}[/bold red]")
            continue

        try:
            json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            console.print(f"[bold red]Invalid JSON: {exc}[/bold red]")
            continue

        console.print(f"[green]Validated:[/green] {path}")
        return path


# ---------------------------------------------------------------------------
# REVIEW_REASON
# ---------------------------------------------------------------------------

async def review_reason(
    reports_dir: Path,
) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """Interactive review of reasoner JSON specs.

    Returns ``(approved_spec_ids, [(spec_id, paradigm_slug, feedback)], formalizer_rerun_slugs)``.
    """
    console.print()
    console.rule("[bold green]Review Reasoner Specs")

    reasoner_dir = reports_dir / "reasoner"
    if not reasoner_dir.is_dir():
        console.print("[bold red]No reasoner directory found.[/bold red]")
        return [], [], []

    spec_files = sorted(reasoner_dir.glob("*.json"))
    if not spec_files:
        console.print("[bold red]No spec files found.[/bold red]")
        return [], [], []

    approved: list[str] = []
    rejections: list[tuple[str, str, str]] = []
    formalizer_reruns: list[str] = []

    for spec_file in spec_files:
        try:
            data = json.loads(spec_file.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            console.print(f"[red]Error reading {spec_file.name}: {exc}[/red]")
            continue

        spec_id = data.get("formulation_id", spec_file.stem)
        paradigm = data.get("paradigm", "unknown")

        # Handle invalid specs from Reasoner validation
        if data.get("status") == "invalid":
            console.print()
            console.rule(f"[bold red]INVALID: {spec_id}[/bold red]")
            console.print(f"[dim]Paradigm:[/dim] {paradigm}")
            problems = data.get("problems", [])
            for p in problems:
                console.print(f"  [red]• [{p.get('type', '?')}][/red] {p.get('detail', '')}")

            rerun: bool = await _ask(
                questionary.confirm(
                    f"Rerun Formalizer for paradigm '{paradigm}'?",
                    default=True,
                ),
            )
            if rerun and paradigm not in formalizer_reruns:
                formalizer_reruns.append(paradigm)
            continue

        name = data.get("name", spec_id)
        description = data.get("description", "")

        console.print()
        console.rule(f"[bold cyan]{name}[/bold cyan]")
        console.print(f"[dim]Spec:[/dim] {spec_id}  [dim]Paradigm:[/dim] {paradigm}")
        if description:
            console.print()
            console.print(Markdown(description))

        # Show variables summary if present
        variables = data.get("variables", [])
        if variables:
            var_names = ", ".join(v.get("name", v.get("symbol", "?")) for v in variables)
            console.print(f"\n[dim]Variables:[/dim] {var_names}")

        # Show actions used if present
        env_mapping = data.get("env_mapping", {})
        actions = env_mapping.get("actions_used", [])
        if actions:
            console.print(f"[dim]Actions:[/dim] {', '.join(actions)}")

        ok: bool = await _ask(
            questionary.confirm(f"Approve spec '{spec_id}'?", default=True),
        )

        if ok:
            approved.append(spec_id)
        else:
            feedback: str = await _ask(
                questionary.text("What needs fixing?"),
            )
            rejections.append((spec_id, paradigm, feedback))

    return approved, rejections, formalizer_reruns


# ---------------------------------------------------------------------------
# REVIEW_BUILD
# ---------------------------------------------------------------------------

async def review_build(
    reports_dir: Path,
    build_results: dict[str, str],
) -> tuple[list[str], list[tuple[str, str, str]], list[str]]:
    """Interactive review of builder results.

    Returns ``(approved_slugs, [(slug, paradigm, feedback)], reasoner_rerun_slugs)``.
    """
    console.print()
    console.rule("[bold green]Review Build Results")

    approved: list[str] = []
    rejections: list[tuple[str, str, str]] = []
    reasoner_reruns: list[str] = []

    # Check for validation reports (invalid builds)
    builder_dir = reports_dir / "builder"
    if builder_dir.is_dir():
        for vfile in sorted(builder_dir.glob("*_validation.json")):
            try:
                data = json.loads(vfile.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("status") != "invalid":
                continue

            fid = data.get("formulation_id", vfile.stem)
            paradigm = data.get("paradigm", "unknown")

            console.print()
            console.rule(f"[bold red]INVALID BUILD: {fid}[/bold red]")
            console.print(f"[dim]Paradigm:[/dim] {paradigm}")
            problems = data.get("problems", [])
            for p in problems:
                console.print(f"  [red]• [{p.get('type', '?')}][/red] {p.get('detail', '')}")

            rerun: bool = await _ask(
                questionary.confirm(
                    f"Rerun Reasoner for paradigm '{paradigm}'?",
                    default=True,
                ),
            )
            if rerun and paradigm not in reasoner_reruns:
                reasoner_reruns.append(paradigm)

    # Review valid builds
    for slug, content in build_results.items():
        console.print()
        console.rule(f"[bold cyan]{slug}[/bold cyan]")
        console.print(Markdown(content))

        # Simple heuristic: flag potential issues
        lower = content.lower()
        if any(word in lower for word in ("error", "fail", "traceback", "exception")):
            console.print(f"[yellow]Potential issues detected in {slug}.[/yellow]")

        ok: bool = await _ask(
            questionary.confirm(f"Approve build '{slug}'?", default=True),
        )
        if ok:
            approved.append(slug)
        else:
            feedback: str = await _ask(
                questionary.text("What needs fixing?"),
            )
            rejections.append((slug, "unknown", feedback))

    return approved, rejections, reasoner_reruns
