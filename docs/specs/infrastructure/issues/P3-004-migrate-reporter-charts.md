---
id: P3-004
title: Migrate reporter and charts output to S3
status: done
kind: strike
phase: 3
heat: output
priority: 2
blocked_by: [P3-001]
created: 2026-04-11
updated: 2026-04-11
---

# P3-004: Migrate reporter and charts output to S3

## Objective
Replace filesystem reads/writes in reporter and charts with S3 operations. Research files read from S3, output artifacts (PDF, LaTeX, PNGs) uploaded to S3.

## Requirements

### Reporter (`reporter.py`)
- `read_research` tool:
  - Replace `(research_dir / path).resolve().read_text()` with `await storage.get_text(f"research/{run_id}/{path}")`
  - Path traversal guard: ensure path doesn't escape the `research/{run_id}/` prefix
  - Reporter needs `run_id` context — pass from Orchestrator
- `compile_report` tool:
  - LaTeX template stays local: `_TEMPLATE_PATH.read_text()` unchanged
  - Write assembled `.tex` to `tempfile.mkdtemp()`
  - Download chart PNGs from S3 to same temp dir (for `\includegraphics`)
  - Run `tectonic` against temp dir
  - Upload `.tex` to S3: `await storage.put(f"experiments/{exp_id}/report.tex", ...)`
  - Upload `.pdf` to S3: `await storage.put(f"experiments/{exp_id}/report.pdf", ...)`
  - Register both artifacts in `artifacts` table
  - Clean up temp dir

### Charts (`charts.py`)
- `create_chart` tool / `_generate_chart_image`:
  - Render matplotlib to `tempfile.NamedTemporaryFile()` or `BytesIO`
  - Upload PNG to S3: `await storage.put(f"experiments/{exp_id}/charts/{chart_id}.png", png_bytes, "image/png")`
  - Register artifact in `artifacts` table
  - Chart spec `image_path` → S3 key (e.g. `experiments/{exp_id}/charts/chart_1.png`)
  - For LaTeX inclusion: `compile_report` downloads PNGs from S3 to temp dir before tectonic run
- Charts module needs `experiment_id` and `storage` access — pass from Orchestrator/Analyst

### Remove filesystem outputs
- Remove `output_dir` parameter from Reporter and chart tools
- No more `OUTPUT_DIR/charts/` or `OUTPUT_DIR/*.pdf` local directories

## Acceptance Criteria
- [x] Reporter reads research files from S3 (`report.md`, `deep/*.md`, `formulations/*.md`)
- [x] Reporter writes `.tex` and `.pdf` to S3 at `experiments/{exp_id}/`
- [x] Chart PNGs uploaded to S3 at `experiments/{exp_id}/charts/`
- [x] LaTeX compilation works: charts downloaded to temp dir, tectonic produces PDF
- [x] All output artifacts registered in `artifacts` table
- [x] No local `output/` directory created
- [x] Path traversal guard on `read_research` works against S3 prefix

## Files Likely Affected
- `phase2-juan/simlab/reporter.py` — read_research, compile_report
- `phase2-juan/simlab/charts.py` — chart PNG generation and storage
- `phase2-juan/simlab/orchestrator.py` — pass run_id/exp_id to Reporter, pass storage to charts

## Context
Phase spec: `docs/specs/infrastructure/phase-3-phase2-integration.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `output`

## Completion Summary

**Commit:** `c03f1db` — `feat[phase2]: migrate model loader, reporter, charts to S3 (P3-002, P3-004)`

### What was built
- Reporter reads research files from S3 (`report.md`, `deep/*.md`, `formulations/*.md`)
- Reporter writes `.tex` and `.pdf` to S3, downloads chart PNGs to tempdir for LaTeX compilation
- Charts module renders matplotlib to BytesIO, uploads PNGs to S3 at `experiments/{exp_id}/charts/`
- All output artifacts registered in `artifacts` table
- Removed `output_dir` parameter from Reporter and chart tools

### Files created/modified
- `phase2-juan/simlab/reporter.py` — read_research from S3, compile_report with S3 upload
- `phase2-juan/simlab/charts.py` — S3-backed chart generation
- `phase2-juan/simlab/orchestrator.py` — pass run_id/exp_id to reporter
- `phase2-juan/simlab/analyst.py` — updated for new tool signatures
