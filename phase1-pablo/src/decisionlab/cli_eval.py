"""CLI: ``decisionlab eval ...`` and ``decisionlab kg ...``.

Two typer sub-apps, mounted by ``cli.py`` onto the main ``decisionlab``
command. Both initialise ``shared`` once at the start of the command and
shut down on exit so the eval surface owns its own infra lifecycle.

The ``eval`` group runs suites and one-shot topics; the ``kg`` group is
inspection/admin (stats, reset, snapshot/restore, raw Cypher).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from decisionlab.eval import kgadmin
from decisionlab.eval.report import write_report
from decisionlab.eval.runner import run_pipeline
from decisionlab.eval.suite import SuiteSpec, parse_stages, run_suite
from decisionlab.router import Stage

console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool) -> None:
    from rich.logging import RichHandler

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )
    for name in ("httpx", "anthropic", "httpcore", "primp", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _client():
    import anthropic

    return anthropic.AsyncAnthropic()


def _search():
    from decisionlab.adapters import default_search_chain

    return default_search_chain()


async def _with_shared(coro_factory):
    """Run *coro_factory* with shared.init / shared.shutdown around it.

    coro_factory is a zero-arg callable that returns the coroutine to await,
    so ``shared.init`` runs first and the awaitable is created with full
    infra available.
    """
    import shared

    await shared.init()
    try:
        return await coro_factory()
    finally:
        await shared.shutdown()


def _run(coro_factory) -> None:
    """Top-level CLI runner: handles the asyncio.run + shared lifecycle +
    common error reporting. Keeps each typer command function compact."""
    import anthropic

    try:
        asyncio.run(_with_shared(coro_factory))
    except anthropic.AuthenticationError:
        console.print(
            "[bold red]Invalid or missing ANTHROPIC_API_KEY. Set it in .env.[/bold red]"
        )
        raise typer.Exit(code=2) from None
    except anthropic.APIConnectionError:
        console.print(
            "[bold red]Cannot reach the Anthropic API — check ANTHROPIC_BASE_URL "
            "and your network.[/bold red]"
        )
        raise typer.Exit(code=2) from None


# ---------------------------------------------------------------------------
# eval app
# ---------------------------------------------------------------------------


eval_app = typer.Typer(
    name="eval",
    help="Evaluation harness: run suites or single topics non-interactively.",
)


def _suite_report_dir(suite_name: str) -> Path:
    return Path("evals/reports") / f"{date.today().isoformat()}-{suite_name}"


def _print_suite_summary(result, report_dir: Path) -> None:
    console.print()
    console.rule(f"[bold]Suite: {result.suite.name}")
    headline = (
        "[bold green]PASS[/bold green]"
        if result.all_passed
        else "[bold red]FAIL[/bold red]"
    )
    console.print(f"Overall: {headline}")
    console.print(f"Topics run: {len(result.topic_results)}/{len(result.suite.topics)}")
    console.print(
        f"Duration: {result.duration_ms / 1000:.1f}s  Cost: ${result.total_usd:.2f}"
    )
    if result.budget_exhausted:
        console.print("[yellow]Budget exhausted — not all topics ran.[/yellow]")
    if result.error:
        console.print(f"[red]Suite error: {result.error}[/red]")
    if result.pre_stats and result.post_stats:
        d_nodes = result.post_stats.total_nodes - result.pre_stats.total_nodes
        d_rels = result.post_stats.total_relations - result.pre_stats.total_relations
        console.print(f"KG growth: nodes {d_nodes:+d}, relations {d_rels:+d}")

    table = Table(title="Topics")
    table.add_column("Topic")
    table.add_column("Run", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Asserts", justify="right")
    for tr in result.topic_results:
        passed_count = tr.total_assertions() - tr.failed_count()
        total = tr.total_assertions()
        status = "[green]ok[/green]" if tr.all_passed else "[red]fail[/red]"
        if not tr.run.succeeded:
            status = f"[red]err: {tr.run.failed_at}[/red]"
        table.add_row(tr.topic, tr.run.run_id, status, f"{passed_count}/{total}")
    console.print(table)
    console.print(f"[dim]Reports: {report_dir}[/dim]")


@eval_app.command("run")
def cli_eval_run(
    suite: Path = typer.Argument(..., exists=True, help="Path to suite YAML"),
    stages_override: list[str] = typer.Option(
        None,
        "--stages",
        help="Override suite's stages (comma-separated, e.g. research,formalize)",
    ),
    no_reset: bool = typer.Option(
        False,
        "--no-reset",
        help="Suppress reset_kg_before, even if the suite enables it",
    ),
    report_dir: Path | None = typer.Option(
        None,
        "--report",
        help="Where to write report.md/json (default: evals/reports/<date>-<name>)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run an eval suite end-to-end and write a markdown + JSON report."""
    _setup_logging(verbose)
    spec = SuiteSpec.from_yaml(suite)
    if stages_override:
        flat = [
            s.strip() for tok in stages_override for s in tok.split(",") if s.strip()
        ]
        spec = _replace_stages(spec, parse_stages(flat))
    if no_reset:
        spec = _replace_reset(spec, False)

    out_dir = report_dir or _suite_report_dir(spec.name)

    async def _factory():
        result = await run_suite(spec, client=_client(), search=_search())
        write_report(result, out_dir)
        _print_suite_summary(result, out_dir)
        if not result.all_passed:
            raise typer.Exit(code=1)
        return result

    _run(_factory)


@eval_app.command("topics")
def cli_eval_topics(
    file: Path = typer.Argument(..., exists=True, help="One topic per line"),
    stages: str = typer.Option(
        "research", "--stages", help="Comma-separated stages (default: research)"
    ),
    env_spec: Path | None = typer.Option(
        None,
        "--env-spec",
        help="env_spec.json — required if stages include reason or build",
    ),
    reset_kg: bool = typer.Option(
        False, "--reset-kg", help="Wipe the KG before the first topic"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Bulk-populate: run each line of *file* as a topic, no assertions."""
    _setup_logging(verbose)
    stage_seq = parse_stages([s.strip() for s in stages.split(",") if s.strip()])
    needs_env = Stage.REASON in stage_seq or Stage.BUILD in stage_seq
    if needs_env and env_spec is None:
        console.print(
            "[bold red]--env-spec is required when stages include reason or build[/bold red]"
        )
        raise typer.Exit(code=2)

    topics = [line.strip() for line in file.read_text().splitlines() if line.strip()]
    if not topics:
        console.print("[yellow]No topics found in file.[/yellow]")
        return

    async def _factory():
        if reset_kg:
            n = await kgadmin.reset(confirm=True)
            console.print(f"[dim]KG reset: deleted {n} nodes[/dim]")
        for i, topic in enumerate(topics, 1):
            console.rule(f"[bold]({i}/{len(topics)}) {topic}")
            result = await run_pipeline(
                topic,
                stages=stage_seq,
                env_spec_path=env_spec,
                project_root=Path("evals/runs"),
                client=_client(),
                search=_search(),
                reset_usage=False,
            )
            ok = "[green]ok[/green]" if result.succeeded else "[red]fail[/red]"
            console.print(
                f"{ok}  paradigms={list(result.paradigms)}  "
                f"nodes_created={result.total_nodes_created()}  "
                f"({result.duration_ms / 1000:.1f}s)"
            )
            if result.failed_at:
                console.print(
                    f"[red]→ failed at {result.failed_at}: {result.error}[/red]"
                )

    _run(_factory)


@eval_app.command("pipeline")
def cli_eval_pipeline(
    topic: str = typer.Argument(..., help="Decision-making problem"),
    stages: str = typer.Option(
        "research", "--stages", help="Comma-separated stages (default: research)"
    ),
    env_spec: Path | None = typer.Option(None, "--env-spec", help="env_spec.json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """One-shot: run a single topic non-interactively, print summary."""
    _setup_logging(verbose)
    stage_seq = parse_stages([s.strip() for s in stages.split(",") if s.strip()])
    if (Stage.REASON in stage_seq or Stage.BUILD in stage_seq) and env_spec is None:
        console.print(
            "[bold red]--env-spec is required when stages include reason or build[/bold red]"
        )
        raise typer.Exit(code=2)

    async def _factory():
        result = await run_pipeline(
            topic,
            stages=stage_seq,
            env_spec_path=env_spec,
            project_root=Path("evals/runs"),
            client=_client(),
            search=_search(),
        )
        console.rule(f"[bold]{topic}")
        console.print(f"run_id: {result.run_id}")
        console.print(f"paradigms: {list(result.paradigms)}")
        console.print(f"formulations: {list(result.formulations)}")
        for stage_name, payload in result.memory_per_stage.items():
            console.print(
                f"memory[{stage_name}]: nodes={payload.get('nodes_created', 0)}, "
                f"rels={payload.get('relations_created', 0)}, "
                f"facts={payload.get('facts_stored', 0)}"
            )
        console.print(
            f"duration: {result.duration_ms / 1000:.1f}s  "
            f"failed_at: {result.failed_at}  "
            f"error: {result.error or '—'}"
        )
        if not result.succeeded:
            raise typer.Exit(code=1)

    _run(_factory)


# ---------------------------------------------------------------------------
# kg app
# ---------------------------------------------------------------------------


kg_app = typer.Typer(
    name="kg", help="Knowledge-graph admin: stats, reset, snapshot/restore, raw query."
)


@kg_app.command("stats")
def cli_kg_stats(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON (for piping)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Print node/relation totals and per-label/per-type breakdowns."""
    _setup_logging(verbose)

    async def _factory():
        s = await kgadmin.stats()
        if as_json:
            console.print_json(json.dumps(s.to_dict()))
            return
        console.print(f"[bold]Total nodes:[/bold] {s.total_nodes}")
        console.print(f"[bold]Active relations:[/bold] {s.total_relations}")
        if s.by_label:
            t = Table(title="Nodes by label")
            t.add_column("Label")
            t.add_column("Count", justify="right")
            for label, n in sorted(s.by_label.items(), key=lambda x: -x[1]):
                t.add_row(label, str(n))
            console.print(t)
        if s.by_type:
            t = Table(title="Active relations by type")
            t.add_column("Type")
            t.add_column("Count", justify="right")
            for rt, n in sorted(s.by_type.items(), key=lambda x: -x[1]):
                t.add_row(rt, str(n))
            console.print(t)

    _run(_factory)


@kg_app.command("reset")
def cli_kg_reset(
    confirm: bool = typer.Option(
        False, "--confirm", help="Required: this is destructive"
    ),
    no_seed: bool = typer.Option(
        False,
        "--no-seed",
        help="Skip seeding canonical paradigms after reset.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Delete every node and relation in the KG, then re-seed canonical paradigms."""
    _setup_logging(verbose)
    if not confirm:
        console.print(
            "[bold red]Refusing to reset without --confirm (destructive).[/bold red]"
        )
        raise typer.Exit(code=2)

    async def _factory():
        n = await kgadmin.reset(confirm=True)
        console.print(f"[bold]Deleted {n} nodes (and all their relations).[/bold]")
        if not no_seed:
            await _seed_canonicals_with_console()

    _run(_factory)


@kg_app.command("seed")
def cli_kg_seed(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Seed canonical Paradigm umbrellas without resetting the KG."""
    _setup_logging(verbose)

    async def _factory():
        await _seed_canonicals_with_console()

    _run(_factory)


async def _seed_canonicals_with_console() -> None:
    """Wire ``seed_canonical_paradigms`` against ``shared``-owned infra and report."""
    import shared
    from decisionlab.knowledge.seed import seed_canonical_paradigms

    counters = await seed_canonical_paradigms(
        shared.kg,
        getattr(shared, "embeddings", None),
        getattr(shared, "vectors", None),
    )
    console.print(
        f"[bold]Canonical paradigms seeded:[/bold] "
        f"created={counters['nodes_created']} "
        f"merged={counters['nodes_merged']} "
        f"vectors={counters['vectors_indexed']}"
    )


@kg_app.command("snapshot")
def cli_kg_snapshot(
    out: Path = typer.Argument(..., help="Where to write the snapshot JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Dump the entire KG (nodes + relations, including superseded)."""
    _setup_logging(verbose)

    async def _factory():
        await kgadmin.snapshot_to_file(out)
        console.print(f"[bold]Snapshot written:[/bold] {out}")

    _run(_factory)


@kg_app.command("restore")
def cli_kg_restore(
    src: Path = typer.Argument(..., exists=True, help="Snapshot JSON to restore"),
    no_reset: bool = typer.Option(
        False,
        "--no-reset",
        help="Skip the wipe-before-restore step (rarely useful)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Wipe + restore from a snapshot (the default safe path)."""
    _setup_logging(verbose)

    async def _factory():
        snap = json.loads(src.read_text())
        await kgadmin.restore(snap, reset_first=not no_reset)
        console.print("[bold]Restore complete.[/bold]")

    _run(_factory)


@kg_app.command("query")
def cli_kg_query(
    cypher: str = typer.Argument(..., help="Cypher query string"),
    params: list[str] = typer.Option(
        None, "-p", "--param", help="key=value parameter binding (repeatable)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run an arbitrary Cypher query and print rows as JSON."""
    _setup_logging(verbose)

    parsed: dict[str, str] = {}
    for kv in params or []:
        if "=" not in kv:
            console.print(f"[bold red]Bad --param (expected k=v): {kv!r}[/bold red]")
            raise typer.Exit(code=2)
        k, v = kv.split("=", 1)
        parsed[k] = v

    async def _factory():
        rows = await kgadmin.query(cypher, parsed)
        console.print_json(json.dumps(rows, default=str))

    _run(_factory)


# ---------------------------------------------------------------------------
# Spec helpers
# ---------------------------------------------------------------------------


def _replace_stages(spec: SuiteSpec, stages: tuple[Stage, ...]) -> SuiteSpec:
    """Replace ``stages`` on a frozen SuiteSpec — used by --stages override."""
    return _clone_spec(spec, stages=stages)


def _replace_reset(spec: SuiteSpec, reset_kg_before: bool) -> SuiteSpec:
    return _clone_spec(spec, reset_kg_before=reset_kg_before)


def _clone_spec(spec: SuiteSpec, **overrides) -> SuiteSpec:
    """Re-construct a frozen SuiteSpec carrying every field forward.

    Uses ``dataclasses.replace`` so future ``SuiteSpec`` fields don't have
    to be threaded through each ``_replace_*`` helper — the previous
    bespoke helpers silently dropped ``suite_assertions``.
    """
    from dataclasses import replace

    return replace(spec, **overrides)
