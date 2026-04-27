# KG-Enrichment Phase 3: Prompt-level enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Analyst and Reporter agents effectively use pre-fetched KG knowledge by adding formulation queries and prompt instructions.

**Architecture:** Config-only change to `_PREFETCH_QUERIES` dict adds formulation namespace. Prompt-only changes to system prompts and sim-recall suffixes tell agents what to do with the injected knowledge context sections.

**Tech Stack:** Python (prompt strings), pytest

---

### Task 1: Add formulation queries to `_PREFETCH_QUERIES` (P3-001)

**Files:**
- Modify: `phase2-juan/simlab/orchestrator.py:113-125`

- [ ] **Step 1: Add formulation query to analyst**

In `phase2-juan/simlab/orchestrator.py`, find the `_PREFETCH_QUERIES` dict (line 113). Add the formulation entry to the `"analyst"` list:

```python
_PREFETCH_QUERIES: dict[str, list[tuple[str, str, str, int]]] = {
    "architect": [
        ("Paradigm facts", "postulates and key properties for {paradigm}", "paradigm", 5),
        ("Previous environments", "environment specifications for {paradigm}", "simulation", 5),
    ],
    "analyst": [
        ("Postulates", "postulates for {paradigm}", "paradigm", 5),
        ("Historical simulations", "previous simulation results for {paradigm}", "simulation", 5),
        ("Formulations", "mathematical formulations and equations for {paradigm}", "formulation", 3),
    ],
    "reporter": [
        ("References", "papers and authors for {paradigm}", "meta", 10),
        ("Formulations", "mathematical formulations for {paradigm}", "formulation", 3),
    ],
}
```

- [ ] **Step 2: Run existing prefetch tests to see what breaks**

Run: `cd phase2-juan && uv run pytest tests/test_kg_prefetch.py -v`

Expected: `test_prefetch_analyst_parallel` and `test_prefetch_reporter` FAIL (query counts changed). Other tests may also fail due to side_effect list lengths.

- [ ] **Step 3: Commit**

```bash
git add phase2-juan/simlab/orchestrator.py
git commit -m "feat[kg-enrichment]: P3-001 — add formulation queries to analyst and reporter prefetch"
```

---

### Task 2: Update prefetch tests (P3-004, part 1)

**Files:**
- Modify: `phase2-juan/tests/test_kg_prefetch.py`

- [ ] **Step 1: Add `_FORMULATIONS` helper constant**

At line 23 (after `_PAPERS`), add:

```python
_FORMULATIONS = "## Retrieved Knowledge (2 results)\n\n### Result 1\nU(x) = x^0.88 for gains..."
```

- [ ] **Step 2: Fix `test_prefetch_analyst_parallel`**

The mock now needs 3 return values (paradigm + simulation + formulation). Update:

```python
@pytest.mark.asyncio
async def test_prefetch_analyst_parallel():
    """Analyst stage: 3 parallel queries (paradigm + simulation + formulation)."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _SIMULATION, _FORMULATIONS])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "analyst")

    assert mock_rc.call_count == 3
    assert "## Knowledge context" in result
    assert "### Postulates" in result
    assert "### Historical simulations" in result
    assert "### Formulations" in result
```

- [ ] **Step 3: Fix `test_prefetch_analyst_omits_empty_subsection`**

Needs 3 side_effect values. Keep formulation as successful:

```python
@pytest.mark.asyncio
async def test_prefetch_analyst_omits_empty_subsection():
    """If one query returns empty, its subsection is omitted."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _EMPTY, _FORMULATIONS])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "analyst")

    assert "### Postulates" in result
    assert "### Historical simulations" not in result
    assert "### Formulations" in result
```

- [ ] **Step 4: Fix `test_prefetch_reporter`**

Now expects 2 queries (meta + formulation):

```python
@pytest.mark.asyncio
async def test_prefetch_reporter():
    """Reporter stage: 2 queries (meta top_k=10 + formulation top_k=3)."""
    mock_rc = AsyncMock(side_effect=[_PAPERS, _FORMULATIONS])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "reporter")

    assert mock_rc.call_count == 2
    assert "## Knowledge context" in result
    assert "### References" in result
    assert "### Formulations" in result
```

- [ ] **Step 5: Fix `test_prefetch_partial_failure`**

Now analyst has 3 queries. First fails, other two succeed:

```python
@pytest.mark.asyncio
async def test_prefetch_partial_failure():
    """One query fails, others succeed — return successful + emit warning."""
    mock_rc = AsyncMock(side_effect=[RuntimeError("connection refused"), _SIMULATION, _FORMULATIONS])
    on_warning = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "analyst", on_warning=on_warning)

    on_warning.assert_called_once()
    assert "### Historical simulations" in result
    assert "### Formulations" in result
    assert "### Postulates" not in result
```

- [ ] **Step 6: Fix `test_prefetch_total_failure`**

Analyst now has 3 queries, all fail:

```python
@pytest.mark.asyncio
async def test_prefetch_total_failure():
    """All queries fail — return '' + emit warnings."""
    mock_rc = AsyncMock(side_effect=[RuntimeError("fail1"), RuntimeError("fail2"), RuntimeError("fail3")])
    on_warning = AsyncMock()

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        result = await prefetch_knowledge("prospect_theory", "analyst", on_warning=on_warning)

    assert result == ""
    assert on_warning.call_count == 3
```

- [ ] **Step 7: Update `test_prefetch_roundtrip`**

Needs 3 side_effect values:

```python
@pytest.mark.asyncio
async def test_prefetch_roundtrip():
    """Full flow: prefetch -> format -> verify structure for agent injection."""
    mock_rc = AsyncMock(side_effect=[_POSTULATES, _SIMULATION, _FORMULATIONS])

    with (
        patch("simlab.recall.retrieve.retrieve_context", mock_rc),
        patch("simlab.recall.retrieve._EMPTY_RESULT", _EMPTY),
    ):
        knowledge_ctx = await prefetch_knowledge("prospect_theory", "analyst")

    prompt = "Analyze patterns"
    tracker_output = "Step 1: agent moved north"
    parts = [prompt]
    if knowledge_ctx:
        parts.append(knowledge_ctx)
    parts.append(f"## Tracker observation log\n\n{tracker_output}")
    user_message = "\n\n".join(parts)

    assert user_message.startswith("Analyze patterns")
    assert "## Knowledge context" in user_message
    assert "### Postulates" in user_message
    assert "### Historical simulations" in user_message
    assert "### Formulations" in user_message
    ctx_pos = user_message.index("## Knowledge context")
    tracker_pos = user_message.index("## Tracker observation log")
    assert ctx_pos < tracker_pos
```

- [ ] **Step 8: Run all prefetch tests**

Run: `cd phase2-juan && uv run pytest tests/test_kg_prefetch.py -v`

Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add phase2-juan/tests/test_kg_prefetch.py
git commit -m "test[kg-enrichment]: P3-004 — update prefetch tests for formulation queries"
```

---

### Task 3: Analyst system prompt + recall suffix (P3-002)

**Files:**
- Modify: `phase2-juan/simlab/analyst.py:190-217` (end of ANALYST_SYSTEM_PROMPT)
- Modify: `phase2-juan/simlab/recall/agent_tools.py:27-35` (_PROMPT_SECTIONS["analyst"])

- [ ] **Step 1: Append knowledge context usage section to Analyst prompt**

In `phase2-juan/simlab/analyst.py`, find the end of `ANALYST_SYSTEM_PROMPT` (the closing `"""`  at line 217). Insert before it:

```python
## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it \
as follows:

### Postulates
Cross-check each observed pattern against the listed postulates. For each \
pattern in your output, state which postulate it confirms, refutes, or is \
unrelated to. Use the postulate identifier (e.g. "P1", "Postulado 2") in the \
evidence field. Example: "Confirma P2 (regulación homeostática): el agente \
redujo su tasa de alimentación al alcanzar energía estable."

### Formulations
Compare the mathematical predictions (utility functions, discount rates, \
update rules) against empirical behavior. If the model predicts U(r) = sqrt(r) \
but agents show linear reward sensitivity, flag the deviation with specific \
values. Reference the equation name or number when available.

### Historical simulations
Compare key metrics (survival rate, resource efficiency, strategy distribution) \
with previous runs. Note if the current result is consistent with or diverges \
from historical trends.

If knowledge context is empty or absent, proceed normally — do not mention its \
absence.
```

- [ ] **Step 2: Update sim-recall analyst prompt suffix**

In `phase2-juan/simlab/recall/agent_tools.py`, replace `_PROMPT_SECTIONS["analyst"]`:

```python
    "analyst": """

## Postulate cross-check

A "## Knowledge context" section with postulates, formulations, and historical \
data is pre-injected in your input. Use it as your primary reference for \
cross-checking. If you need deeper or more specific knowledge (e.g., a \
particular postulate detail, a specific past experiment), call \
`retrieve_context` with a targeted query.
""",
```

- [ ] **Step 3: Run tests**

Run: `cd phase2-juan && uv run pytest tests/test_kg_prefetch.py -v`

Expected: ALL PASS (prompt changes don't affect existing test assertions)

- [ ] **Step 4: Commit**

```bash
git add phase2-juan/simlab/analyst.py phase2-juan/simlab/recall/agent_tools.py
git commit -m "feat[kg-enrichment]: P3-002 — analyst prompt instructions for knowledge context"
```

---

### Task 4: Reporter system prompt + recall suffix (P3-003)

**Files:**
- Modify: `phase2-juan/simlab/reporter.py:293-306` (end of REPORTER_SYSTEM_PROMPT)
- Modify: `phase2-juan/simlab/recall/agent_tools.py:36-45` (_PROMPT_SECTIONS["reporter"])

- [ ] **Step 1: Append knowledge context usage section to Reporter prompt**

In `phase2-juan/simlab/reporter.py`, find the end of `REPORTER_SYSTEM_PROMPT` (the closing `"""` at line 306). Insert before it:

```python
## Knowledge context usage

When a "## Knowledge context" section is present in the user message, use it \
as follows:

### References (meta)
Use the returned Paper nodes to build real citations in the report body. \
Format: \\textit{Title} (Author, Year). If a DOI is available, include it in \
the References section at the end. Do NOT fabricate citations — use only what \
was returned. If zero results were returned, fall back to generic references \
from read_research files.

### Formulations
Include the relevant equations in the "Modelo de Decisión" section using LaTeX \
math environments (\\begin{equation} or \\begin{align}). Reference them by \
number when discussing model behavior in the Análisis section. This gives the \
report mathematical grounding from the Knowledge Graph's validated formulation \
nodes, complementing what read_research provides.

If knowledge context is empty or absent, proceed with read_research as the sole \
source — do not mention knowledge context absence in the report.
```

- [ ] **Step 2: Update sim-recall reporter prompt suffix**

In `phase2-juan/simlab/recall/agent_tools.py`, replace `_PROMPT_SECTIONS["reporter"]`:

```python
    "reporter": """

## References grounding

A "## Knowledge context" section with paper references and formulations is \
pre-injected in your input. Use it for citations and equations. If you need \
additional references or formulations not covered by the pre-fetch (e.g., a \
related paradigm), call `retrieve_context` with a targeted query.
""",
```

- [ ] **Step 3: Run all tests**

Run: `cd phase2-juan && uv run pytest tests/test_kg_prefetch.py -v`

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add phase2-juan/simlab/reporter.py phase2-juan/simlab/recall/agent_tools.py
git commit -m "feat[kg-enrichment]: P3-003 — reporter prompt instructions for knowledge context"
```

---

### Task 5: Mark issues done + update phases

**Files:**
- Modify: `docs/specs/kg-enrichment/issues/P3-001-prefetch-formulation-queries.md`
- Modify: `docs/specs/kg-enrichment/issues/P3-002-analyst-prompt-enrichment.md`
- Modify: `docs/specs/kg-enrichment/issues/P3-003-reporter-prompt-enrichment.md`
- Modify: `docs/specs/kg-enrichment/issues/P3-004-update-prefetch-tests.md`
- Modify: `docs/specs/kg-enrichment/phases.md`

- [ ] **Step 1: Update all issue statuses to `done`**

In each P3-00X issue file, change `status: todo` to `status: done`.

- [ ] **Step 2: Mark Phase 3 complete in phases.md**

Change `- [ ] **Phase 3:` to `- [x] **Phase 3:`.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/kg-enrichment/
git commit -m "docs[kg-enrichment]: mark Phase 3 issues done"
```
