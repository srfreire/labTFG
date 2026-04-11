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
        import uuid as _uuid

        import shared

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            r = Researcher(client=_client(), search=DuckDuckGoAdapter(), run_id=run_id)
            return await r.run(problem)
        finally:
            await shared.shutdown()

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
        import uuid as _uuid

        import shared

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            dr = DeepResearcher(client=_client(), search=DuckDuckGoAdapter(), run_id=run_id)
            return await dr.run(paradigm)
        finally:
            await shared.shutdown()

    result = _run_async(_run())

    console.print()
    console.rule("[bold cyan]Deep Research Summary")
    console.print(Markdown(result))
    console.print()
    console.print(f"[bold]Full report saved to S3[/bold]")


@app.command()
def formalize(
    reports_dir: Path = typer.Option(..., "--reports-dir", help="Path to existing research run"),
    paradigms: list[str] = typer.Option([], "--paradigms", help="Paradigm slugs to formalize (discovers from S3 if empty)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Formalizer agent — produces formal mathematical models from deep research."""
    _setup_logging(verbose)

    from decisionlab.agents.formalizer import Formalizer

    async def _run():
        import uuid as _uuid

        import shared

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            research_prefix = f"research/{run_id}"
            f = Formalizer(client=_client(), research_prefix=research_prefix, run_id=run_id)
            return await f.run(paradigms)
        finally:
            await shared.shutdown()

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
    paradigms: list[str] = typer.Option([], "--paradigms", help="Paradigm slugs to reason about (discovers from S3 if empty)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Reasoner agent — produces agent specs from formalized models and an environment."""
    _setup_logging(verbose)

    if not env_spec.exists():
        console.print(f"[bold red]Error: env_spec file not found at {env_spec}[/bold red]")
        raise typer.Exit(code=1)

    from decisionlab.agents.reasoner import Reasoner

    async def _run():
        import uuid as _uuid

        import shared

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            research_prefix = f"research/{run_id}"
            models_prefix = f"models/{run_id}"
            # Upload env_spec to S3 so the agent can read it
            env_content = env_spec.read_text()
            await shared.storage.put_text(f"{research_prefix}/env_spec.json", env_content)

            r = Reasoner(
                client=_client(),
                research_prefix=research_prefix,
                models_prefix=models_prefix,
                run_id=run_id,
            )
            return await r.run(paradigms)
        finally:
            await shared.shutdown()

    report = _run_async(_run())

    console.print()
    for paradigm, content in report.specs.items():
        console.rule(f"[bold cyan]{paradigm}")
        console.print(Markdown(content))
        console.print()


@app.command()
def build(
    reports_dir: Path = typer.Option(..., "--reports-dir", help="Path to existing research run"),
    paradigms: list[str] = typer.Option([], "--paradigms", help="Spec IDs to build (discovers from S3 if empty)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the Builder agent — generates DecisionModel implementations from JSON specs."""
    _setup_logging(verbose)

    from decisionlab.agents.builder import Builder

    async def _run():
        import uuid as _uuid

        import shared

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            models_prefix = f"models/{run_id}"
            b = Builder(
                client=_client(),
                models_prefix=models_prefix,
                run_id=run_id,
                project_root=Path.cwd(),
            )
            return await b.run(paradigms or None)
        finally:
            await shared.shutdown()

    report = _run_async(_run())

    console.print()
    for paradigm, content in report.results.items():
        console.rule(f"[bold cyan]{paradigm}")
        console.print(Markdown(content))
        console.print()


@app.command()
def run(
    problem: str = typer.Argument(help="Decision-making problem to investigate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Run the full pipeline with interactive human feedback."""
    _setup_logging(verbose)

    from decisionlab.router import PipelineState, Router, Stage

    async def _run():
        import uuid as _uuid

        import shared
        from shared.models import Run

        await shared.init()
        try:
            run_id = str(_uuid.uuid4())
            async with shared.db.get_session() as session:
                db_run = Run(
                    id=_uuid.UUID(run_id),
                    problem_description=problem,
                    status="running",
                    s3_prefix=f"research/{run_id}",
                )
                session.add(db_run)
                await session.commit()

            reports_dir = _reports_dir(problem)
            state = PipelineState(
                stage=Stage.RESEARCH, problem=problem,
                reports_dir=reports_dir, run_id=run_id,
            )
            state.save()
            router = Router(
                client=_client(), state=state,
                search=DuckDuckGoAdapter(), project_root=Path.cwd(),
            )
            await router.run()
        finally:
            await shared.shutdown()

    _run_async(_run())


@app.command()
def resume(
    reports_dir: Path = typer.Option(None, "--reports-dir", help="Path to existing pipeline run"),
    run_id: str = typer.Option(None, "--run-id", help="Run ID to resume (requires --reports-dir for now)"),
    from_stage: str = typer.Option(None, "--from", help="Jump to specific stage"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logs"),
):
    """Resume a pipeline from saved state or from a specific stage."""
    _setup_logging(verbose)

    if run_id and not reports_dir:
        console.print("[bold red]--run-id without --reports-dir not yet supported (coming in P2-004)[/bold red]")
        raise typer.Exit(code=1)
    if not reports_dir:
        console.print("[bold red]Provide --reports-dir or --run-id[/bold red]")
        raise typer.Exit(code=1)

    from decisionlab.router import PipelineState, Router, Stage

    async def _run():
        import shared

        await shared.init()
        try:
            state = PipelineState.load(reports_dir)
            if from_stage:
                state.stage = Stage[from_stage.upper()]
                state.save()
            router = Router(
                client=_client(), state=state,
                search=DuckDuckGoAdapter(), project_root=Path.cwd(),
            )
            await router.run()
        finally:
            await shared.shutdown()

    _run_async(_run())


if __name__ == "__main__":
    app()
