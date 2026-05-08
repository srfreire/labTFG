---
id: P1-004
title: Delete canonicalize.py, tau calibration script, and dead validators
status: todo
kind: strike
phase: 1
heat: extraction
priority: 2
blocked_by: [P1-003]
created: 2026-05-08
updated: 2026-05-08
---

# P1-004: Delete the merger

## Objective

Remove the post-hoc canonicalization machinery now that extraction
emits canonical slugs directly. Deletes the entire
`canonicalize.py` module, the τ-calibration script, and the duct-tape
validators in `kg_writer.py` that existed to catch slug-leak bugs the
new schema makes impossible.

## Requirements

Per phase spec R4:

1. Confirm a regression run of `cumulative-growth` +
   `slug-accuracy` passes (≥8/8 hit rate, growth caps respected) with
   P1-001 / P1-002 / P1-003 in place. If it doesn't, **stop here** —
   raise the issue and don't delete.
2. Delete:
   - `phase1-pablo/src/decisionlab/canonicalize.py`
   - `phase1-pablo/scripts/calibrate_canonicalize_tau.py`
3. Remove imports + call sites:
   - `phase1-pablo/src/decisionlab/agents/memory_agent.py:15` —
     `from decisionlab.canonicalize import canonicalize`. The
     conditional call from P1-003 also goes (now unreachable).
   - `phase1-pablo/src/decisionlab/feedback_port.py:403` —
     `from decisionlab.canonicalize import DEFAULT_THRESHOLD`.
4. Remove duct-tape from `kg_writer.py`:
   - `_validate_natural_key` UUID-shape rejection block (~lines
     104–119) — slugs are now Literal-validated upstream.
   - `_is_garbage_paradigm_slug` filter in `extraction.py` (~lines
     176–188) — Literal validation supersedes it.
5. Update `docs/memory-system.md` §A1 with a "DONE 2026-MM-DD"
   marker.

## Acceptance Criteria

- [ ] AC1: `phase1-pablo/src/decisionlab/canonicalize.py` and
      `phase1-pablo/scripts/calibrate_canonicalize_tau.py` deleted.
- [ ] AC2: `grep -rn 'from decisionlab.canonicalize\|import
      decisionlab.canonicalize\|canonicalize\.' phase1-pablo/src/`
      returns zero matches.
- [ ] AC3: `_validate_natural_key` UUID-shape branch and
      `_is_garbage_paradigm_slug` removed; remaining validation in
      `kg_writer.py` is only the safe-identifier and length-cap
      checks.
- [ ] AC4: `docs/memory-system.md` §A1 marked "DONE".
- [ ] AC5: Full eval suite (smoke + cumulative-growth +
      slug-accuracy) green.

## Files Likely Affected

- `phase1-pablo/src/decisionlab/canonicalize.py` — DELETE.
- `phase1-pablo/scripts/calibrate_canonicalize_tau.py` — DELETE.
- `phase1-pablo/src/decisionlab/agents/memory_agent.py` — remove
  import + call.
- `phase1-pablo/src/decisionlab/feedback_port.py` — remove import.
- `phase1-pablo/src/decisionlab/knowledge/kg_writer.py` — remove
  `_validate_natural_key` UUID branch.
- `phase1-pablo/src/decisionlab/knowledge/extraction.py` — remove
  `_is_garbage_paradigm_slug`.
- `docs/memory-system.md` — mark §A1 done.

## Context

Phase spec: `docs/specs/memory-refactor/phase-1-canonical-ids.md` (R4)
Heat: `extraction` (last in the chain — depends on P1-003)
