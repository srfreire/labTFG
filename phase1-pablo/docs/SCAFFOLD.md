# Phase 1: Project Scaffold

## Repo structure

```
labTFG/
  CLAUDE.md
  docs/
  phase2-juan/
  phase1-pablo/
    pyproject.toml
    .env                          # API keys (gitignored)
    .env.example                  # template with empty values
    src/decisionlab/
      __init__.py
      cli.py                      # Typer app, entry point
      router.py                   # Pipeline orchestration + human feedback
      agents/
        __init__.py
        researcher.py             # Researcher agent + sub-agent spawning
        reasoner.py               # Reasoner agent
        builder.py                # Builder agent + test loop
      tools/
        __init__.py
        web_search.py             # Brave Search API
        semantic_scholar.py       # Semantic Scholar API
        file_io.py                # read/write files
        code_runner.py            # run pytest subprocess
    tests/
      __init__.py
      test_researcher.py
      test_reasoner.py
      test_builder.py
      test_router.py
    outputs/                      # gitignored, per-run results
      <run_id>/
        01_researcher/
        02_reasoner/
        03_builder/
```

## Stack

| Concern | Choice |
|---|---|
| Package manager | uv |
| CLI | Typer + Rich |
| Interactive prompts | questionary |
| LLM agents | Anthropic Agent SDK |
| Researcher/Sub-agents LLM | Claude Sonnet |
| Reasoner/Builder LLM | Claude Opus |
| Router LLM | Claude Sonnet (candidate for Haiku downgrade) |
| Web search | Brave Search API |
| Papers | Semantic Scholar API |
| Secrets | .env + python-dotenv |
| Testing | pytest + mocks for API calls |
