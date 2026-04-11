---
id: P2-002
title: Migrate Phase 1 report tools to StorageService
status: done
kind: strike
phase: 2
heat: tools
priority: 2
blocked_by: [P2-001]
created: 2026-04-11
updated: 2026-04-11
---

# P2-002: Migrate Phase 1 report tools to StorageService

## Objective
Replace all filesystem writes/reads in `tools/reports.py` with StorageService calls.

## Requirements
- `save_deep_report(run_id, paradigm, content)`:
  - `await storage.put_text(f"research/{run_id}/deep/{slug}.md", content)`
  - Register artifact in `artifacts` table (type: `deep_report`)
- `save_summary_report(run_id, summary)`:
  - `await storage.put_text(f"research/{run_id}/report.md", summary)`
  - Register artifact (type: `report`)
- `generate_tree_map(state)`:
  - Read existing report: `await storage.get_text(f"research/{run_id}/report.md")`
  - Read deep reports for paradigm names: `await storage.get_text(f"research/{run_id}/deep/{slug}.md")`
  - Write updated report back: `await storage.put_text(...)`
- `create_read_report(run_id)` → inner `read_report` function:
  - `await storage.get_text(f"research/{run_id}/deep/{slug}.md")`
- All functions become async (they use `await storage.*`)
- Update callers in `researcher.py` and `deep_researcher.py` to await

## Acceptance Criteria
- [x] Deep reports appear in MinIO at `research/{run_id}/deep/{slug}.md`
- [x] Summary report appears in MinIO at `research/{run_id}/report.md`
- [x] Tree map generation reads from and writes to S3
- [x] Read report tool reads from S3
- [x] Each report is registered in `artifacts` table with correct type
- [x] No local filesystem writes in `tools/reports.py`

## Files Likely Affected
- `phase1-pablo/src/decisionlab/tools/reports.py` — all 4 functions
- `phase1-pablo/src/decisionlab/agents/researcher.py` — await save_summary_report, read_report
- `phase1-pablo/src/decisionlab/agents/deep_researcher.py` — await save_deep_report

## Context
Phase spec: `docs/specs/infrastructure/phase-2-phase1-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `tools`
