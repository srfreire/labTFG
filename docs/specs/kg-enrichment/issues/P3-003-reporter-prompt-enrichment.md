---
id: P3-003
title: Add knowledge context usage instructions to Reporter system prompt
status: done
kind: strike
phase: 3
heat: prompts
blocked_by: [P3-001]
---

# P3-003: Add knowledge context usage instructions to Reporter system prompt

## What

Append a "## Knowledge context usage" section to `REPORTER_SYSTEM_PROMPT` in
`reporter.py` with instructions for:

- **References (meta)**: build real citations with `\textit{Title} (Author, Year)`, include DOIs
- **Formulations**: include equations in LaTeX math environments, reference by number

Also update `_PROMPT_SECTIONS["reporter"]` in `recall/agent_tools.py` to reflect
that pre-fetch already provides baseline context (tool is for ad-hoc depth).

## Why

Same as P3-002 — Reporter needs explicit instructions to integrate KG context
into the LaTeX report structure.

## Acceptance criteria

- `REPORTER_SYSTEM_PROMPT` contains "Knowledge context usage" section
- Section covers references and formulations with LaTeX formatting guidance
- `_PROMPT_SECTIONS["reporter"]` references pre-injected context
- Graceful no-op: prompt says to use read_research as sole source if context is empty
