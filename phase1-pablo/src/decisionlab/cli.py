import typer

app = typer.Typer(name="decisionlab", help="Decision-making paradigm modeling pipeline", invoke_without_command=True)


@app.callback()
def main():
    """Decision-making paradigm modeling pipeline."""


@app.command()
def run(problem: str = typer.Argument(help="Decision-making problem to investigate")):
    """Run the full pipeline: research -> formalize -> build."""
    typer.echo(f"Pipeline not yet implemented. Problem: {problem}")


if __name__ == "__main__":
    app()
