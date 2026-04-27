---
id: P3-002
title: Add knowledge context usage instructions to Analyst system prompt
status: done
kind: strike
phase: 3
heat: prompts
blocked_by: [P3-001]
---

# P3-002: Add knowledge context usage instructions to Analyst system prompt

## What

Append a "## Knowledge context usage" section to `ANALYST_SYSTEM_PROMPT` in
`analyst.py` with instructions for:

- **Postulates**: cross-check each pattern against listed postulates, cite IDs (P1, P2...)
- **Formulations**: compare theoretical predictions vs empirical behavior, flag deviations
- **Historical simulations**: compare metrics with previous runs, note trends

Also update `_PROMPT_SECTIONS["analyst"]` in `recall/agent_tools.py` to reflect
that pre-fetch already provides baseline context (tool is for ad-hoc depth).

## Why

The pre-fetch infrastructure injects knowledge context but agents have no
instructions on what to do with it. Without guidance, the LLM may ignore or
superficially acknowledge the context.

## Acceptance criteria

- `ANALYST_SYSTEM_PROMPT` contains "Knowledge context usage" section
- Section covers postulates, formulations, and historical simulations
- `_PROMPT_SECTIONS["analyst"]` references pre-injected context
- Graceful no-op: prompt says to proceed normally if context is empty
