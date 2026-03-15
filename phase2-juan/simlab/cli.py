"""CLI entry point — interactive chat with the Orchestrator."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from simlab.orchestrator import Orchestrator

load_dotenv()

console = Console()

BANNER = """
[bold cyan]DecisionLab[/bold cyan] — Laboratorio Virtual de Simulación
[dim]Escribe tu petición o 'salir' para terminar.[/dim]
"""

DEFAULT_RESEARCH_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _create_orchestrator() -> Orchestrator:
    """Create an Orchestrator with default configuration."""
    client = anthropic.AsyncAnthropic()
    return Orchestrator(
        client=client,
        research_dir=DEFAULT_RESEARCH_DIR,
        output_dir=DEFAULT_OUTPUT_DIR,
    )


async def _chat_loop(orch: Orchestrator) -> None:
    """Run the interactive chat loop."""
    while True:
        try:
            user_input = console.input("\n[bold green]>[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Hasta luego.[/dim]")
            break

        if user_input.strip().lower() in ("salir", "exit", "quit", "q"):
            console.print("[dim]Hasta luego.[/dim]")
            break

        if not user_input.strip():
            continue

        with console.status("[bold cyan]Pensando...[/bold cyan]", spinner="dots"):
            try:
                response = await orch.chat(user_input)
            except Exception as e:
                console.print(f"[bold red]Error: {e}[/bold red]")
                continue

        console.print()
        console.print(Markdown(response))


def main():
    """Entry point for the CLI."""
    console.print(Panel(BANNER, border_style="cyan"))

    try:
        orch = _create_orchestrator()
    except anthropic.AuthenticationError:
        console.print("[bold red]Error: ANTHROPIC_API_KEY no configurada. Crea un .env con tu key.[/bold red]")
        sys.exit(1)

    try:
        asyncio.run(_chat_loop(orch))
    except KeyboardInterrupt:
        console.print("\n[dim]Hasta luego.[/dim]")


if __name__ == "__main__":
    main()
