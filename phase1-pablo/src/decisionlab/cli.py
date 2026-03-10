"""CLI entry point for running agents individually or as a full pipeline."""

import asyncio
import logging

import anthropic
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown

from decisionlab.adapters.duckduckgo import DuckDuckGoAdapter

load_dotenv()

app = typer.Typer(name="decisionlab", help="Decision-making paradigm modeling pipeline")
console = Console()


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


@app.command()
def research(
    problem: str = typer.Argument(help="Decision-making problem to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Researcher agent — discovers paradigms via breadth-first search."""
    _setup_logging(verbose)

    from decisionlab.agents.researcher import Researcher

    async def _run():
        r = Researcher(client=_client(), search=DuckDuckGoAdapter())
        return await r.run(problem)

    report = asyncio.run(_run())

    console.print()
    console.rule("[bold green]Research Report")
    console.print(Markdown(report.summary))
    for name, deep in report.deep_reports.items():
        console.print()
        console.rule(f"[bold cyan]Deep: {name}")
        console.print(Markdown(deep))


@app.command()
def deep_research(
    paradigm: str = typer.Argument(help="Paradigm to investigate in depth"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the DeepResearcher agent — deep-dives into a single paradigm."""
    _setup_logging(verbose)

    from decisionlab.agents.deep_researcher import DeepResearcher

    async def _run():
        dr = DeepResearcher(client=_client(), search=DuckDuckGoAdapter())
        return await dr.run(paradigm)

    result = asyncio.run(_run())

    console.print()
    console.rule("[bold cyan]Deep Research Report")
    console.print(Markdown(result))


@app.command()
def run(
    problem: str = typer.Argument(help="Decision-making problem to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the full pipeline: research -> reason -> build (only research implemented)."""
    _setup_logging(verbose)

    from decisionlab.agents.researcher import Researcher

    async def _run():
        r = Researcher(client=_client(), search=DuckDuckGoAdapter())
        return await r.run(problem)

    report = asyncio.run(_run())

    console.print()
    console.rule("[bold green]Pipeline — Research Phase Complete")
    console.print(Markdown(report.summary))
    for name, deep in report.deep_reports.items():
        console.print()
        console.rule(f"[bold cyan]Deep: {name}")
        console.print(Markdown(deep))


if __name__ == "__main__":
    app()
