"""CLI entry point for running agents individually or as a full pipeline."""

import asyncio
import logging
import shutil
from datetime import date
from pathlib import Path

import anthropic
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter
from decisionlab.tools.reports import slugify

load_dotenv()

app = typer.Typer(name="decisionlab", help="Decision-making paradigm modeling pipeline")
console = Console()

REPORTS_ROOT = Path("reports")


def _reports_dir(problem: str) -> Path:
    words = slugify(problem).split("-")[:5]
    slug = "-".join(words)
    return REPORTS_ROOT / f"{date.today()}-{slug}"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    # Quiet noisy libraries
    for name in ("httpx", "anthropic", "httpcore", "primp", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic()


def _print_research_report(title: str, report, reports_dir: Path) -> None:
    """Render a ResearchReport to the console."""
    console.print()
    console.rule(f"[bold green]{title}")
    console.print(Markdown(report.summary))
    for name, deep in report.deep_reports.items():
        console.print()
        console.rule(f"[bold cyan]Deep: {name}")
        console.print(Markdown(deep))
    console.print()
    console.print(f"[bold]Reports saved to: {reports_dir}/[/bold]")


def _run_async(coro):
    """Run an async coroutine with user-friendly error handling."""
    try:
        return asyncio.run(coro)
    except anthropic.AuthenticationError:
        console.print("[bold red]Error: Invalid or missing ANTHROPIC_API_KEY. Set it in .env or as an environment variable.[/bold red]")
        raise typer.Exit(code=1)
    except anthropic.APIConnectionError:
        console.print("[bold red]Error: Could not connect to the API. Check your network and ANTHROPIC_BASE_URL.[/bold red]")
        raise typer.Exit(code=1)
    except RuntimeError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def research(
    problem: str = typer.Argument(help="Decision-making problem to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Researcher agent — discovers paradigms via breadth-first search."""
    _setup_logging(verbose)

    from decisionlab.agents.researcher import Researcher

    reports_dir = _reports_dir(problem)

    async def _run():
        r = Researcher(client=_client(), search=DuckDuckGoAdapter(), reports_dir=reports_dir)
        return await r.run(problem)

    report = _run_async(_run())
    _print_research_report("Research Report", report, reports_dir)


@app.command()
def deep_research(
    paradigm: str = typer.Argument(help="Paradigm to investigate in depth"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the DeepResearcher agent — deep-dives into a single paradigm."""
    _setup_logging(verbose)

    from decisionlab.agents.deep_researcher import DeepResearcher

    reports_dir = _reports_dir(paradigm)

    async def _run():
        dr = DeepResearcher(client=_client(), search=DuckDuckGoAdapter(), reports_dir=reports_dir)
        return await dr.run(paradigm)

    result = _run_async(_run())

    console.print()
    console.rule("[bold cyan]Deep Research Summary")
    console.print(Markdown(result))
    console.print()
    console.print(f"[bold]Full report saved to: {reports_dir}/[/bold]")


@app.command()
def formalize(
    reports_dir: Path = typer.Option(..., "--reports-dir", help="Path to existing research run"),
    paradigms: list[str] = typer.Option([], "--paradigms", help="Paradigm slugs to formalize (discovers from disk if empty)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Formalizer agent — produces formal mathematical models from deep research."""
    _setup_logging(verbose)

    deep_dir = reports_dir / "deep"
    if not deep_dir.exists():
        console.print(f"[bold red]Error: deep/ subdirectory not found in {reports_dir}[/bold red]")
        raise typer.Exit(code=1)

    from decisionlab.agents.formalizer import Formalizer

    async def _run():
        f = Formalizer(client=_client(), reports_dir=reports_dir)
        return await f.run(paradigms)

    report = _run_async(_run())

    console.print()
    for paradigm, content in report.formulations.items():
        console.rule(f"[bold cyan]{paradigm}")
        console.print(Markdown(content))
        console.print()


@app.command()
def reason(
    reports_dir: Path = typer.Option(..., "--reports-dir", help="Path to existing research run"),
    env_spec: Path = typer.Option(..., "--env-spec", help="Path to env_spec.json (environment specification)"),
    paradigms: list[str] = typer.Option([], "--paradigms", help="Paradigm slugs to reason about (discovers from disk if empty)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Reasoner agent — produces agent specs from formalized models and an environment."""
    _setup_logging(verbose)

    formulations_dir = reports_dir / "formulations"
    if not formulations_dir.exists():
        console.print(f"[bold red]Error: formulations/ subdirectory not found in {reports_dir}[/bold red]")
        raise typer.Exit(code=1)

    if not env_spec.exists():
        console.print(f"[bold red]Error: env_spec file not found at {env_spec}[/bold red]")
        raise typer.Exit(code=1)

    shutil.copy2(env_spec, reports_dir / "env_spec.json")

    from decisionlab.agents.reasoner import Reasoner

    async def _run():
        r = Reasoner(client=_client(), reports_dir=reports_dir)
        return await r.run(paradigms)

    report = _run_async(_run())

    console.print()
    for paradigm, content in report.specs.items():
        console.rule(f"[bold cyan]{paradigm}")
        console.print(Markdown(content))
        console.print()


@app.command()
def run(
    problem: str = typer.Argument(help="Decision-making problem to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the full pipeline: research -> reason -> build (only research implemented)."""
    _setup_logging(verbose)

    from decisionlab.agents.researcher import Researcher

    reports_dir = _reports_dir(problem)

    async def _run():
        r = Researcher(client=_client(), search=DuckDuckGoAdapter(), reports_dir=reports_dir)
        return await r.run(problem)

    report = _run_async(_run())
    _print_research_report("Pipeline \u2014 Research Phase Complete", report, reports_dir)


if __name__ == "__main__":
    app()
