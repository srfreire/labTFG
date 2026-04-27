---
id: P4-002
title: Add knowledge context usage instructions to Architect system prompt
status: done
kind: strike
phase: 4
heat: prompts
blocked_by: [P4-001]
---

# P4-002: Add knowledge context usage instructions to Architect system prompt

## What

Append "## Knowledge context usage" section to `ARCHITECT_SYSTEM_PROMPT` and update `_PROMPT_SECTIONS["architect"]` in `recall/agent_tools.py`.

## Acceptance criteria

- `ARCHITECT_SYSTEM_PROMPT` contains "Knowledge context usage" section
- Section covers paradigm facts, previous environments, and formulations
- `_PROMPT_SECTIONS["architect"]` references pre-injected context
