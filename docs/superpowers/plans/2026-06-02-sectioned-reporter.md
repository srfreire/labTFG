# Sectioned Reporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Avoid Reporter `max_tokens` failures by generating LaTeX in small sections and compiling the backend-assembled document.

**Architecture:** The backend owns report structure, asks the LLM for bounded section bodies, sanitizes each body, concatenates sections, and compiles once. Existing `compile_report` remains for compatibility and fallback.

**Tech Stack:** Python async, Anthropic-style `client.messages.create`, Tectonic, matplotlib fallback, pytest.

---

### Task 1: Sectioned Reporter Path

**Files:**
- Modify: `phase2-juan/simlab/reporter.py`
- Test: `phase2-juan/tests/test_reporter_latex.py`

- [ ] Add tests proving sectioned generation calls the model multiple times with lower token budget and compiles one assembled PDF.
- [ ] Extract PDF compile/store logic so both tool-based and sectioned paths can use it.
- [ ] Add `_generate_sectioned_report` with fixed sections and compact per-section prompts.
- [ ] Route `Reporter.run` through sectioned generation for normal report generation.
- [ ] Keep existing deterministic fallback for timeouts or section failures.
- [ ] Verify with `uv run pytest tests/test_reporter_latex.py tests/test_api_report_download.py -q`.
