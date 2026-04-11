---
id: P2-003
title: Migrate Phase 1 file tools and builder pytest to StorageService
status: todo
kind: strike
phase: 2
heat: tools
priority: 2
blocked_by: [P2-001]
created: 2026-04-11
updated: 2026-04-11
---

# P2-003: Migrate Phase 1 file tools and builder pytest to StorageService

## Objective
Replace the generic `write_file`/`read_file` LLM tools with S3-backed versions and handle Builder's pytest requirement via temp directories.

## Requirements
- `create_write_file(s3_prefix)` → inner `write_file(params)`:
  - `await storage.put_text(f"{s3_prefix}/{params['path']}", params["content"])`
  - Register artifact in `artifacts` table (type inferred from path: `formulations/*.md` → `formulation`, `reasoner/*.json` → `reasoner_spec`, `builder/*_model.py` → `model`, `builder/test_*.py` → `test`, `builder/*_validation.json` → `reasoner_spec`)
  - Path traversal guard: ensure `params["path"]` doesn't escape the prefix
- `create_read_file(s3_prefix)` → inner `read_file(params)`:
  - `await storage.get_text(f"{s3_prefix}/{params['path']}")`
- Builder pytest handling in `builder_sub.py`:
  - After Builder writes `*_model.py` and `test_*.py` to S3
  - Download both to `tempfile.mkdtemp()`
  - Run `pytest` against the temp dir
  - Clean up temp dir after (regardless of pass/fail)
  - If tests fail and Builder rewrites, re-download and re-test
- Formalizer, Reasoner sub-agents: update constructor to pass S3 prefix instead of local base_dir

## Acceptance Criteria
- [ ] Formulations appear in MinIO at `research/{run_id}/formulations/{slug}.md`
- [ ] Reasoner specs appear in MinIO at `models/{run_id}/reasoner/{fid}.json`
- [ ] Builder models appear in MinIO at `models/{run_id}/builder/{fid}_model.py`
- [ ] Builder tests appear in MinIO at `models/{run_id}/builder/test_{fid}.py`
- [ ] Builder pytest runs from temp dir, passes for valid models
- [ ] Builder retry loop (max 3 attempts) works with S3 round-trip
- [ ] Validation JSON files appear in MinIO when model is unimplementable
- [ ] All artifacts registered in `artifacts` table
- [ ] No local filesystem writes except temp dirs (cleaned up after use)

## Files Likely Affected
- `phase1-pablo/src/decisionlab/tools/files.py` — `create_write_file`, `create_read_file`
- `phase1-pablo/src/decisionlab/agents/builder_sub.py` — pytest temp dir handling
- `phase1-pablo/src/decisionlab/agents/formalizer_sub.py` — pass S3 prefix
- `phase1-pablo/src/decisionlab/agents/reasoner_sub.py` — pass S3 prefix

## Context
Phase spec: `docs/specs/infrastructure/phase-2-phase1-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `tools`
