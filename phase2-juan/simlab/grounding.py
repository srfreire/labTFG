"""Deterministic grounding layer for LLM-authored observation prose.

The Tracker and Analyst copy structured aggregates (action counts, consumption)
correctly into their schema slots, but fabricate numbers in *free prose*
(episode/pattern descriptions): e.g. "60 de 72 acciones totales" when the true
split is 50 of 60, or "(58 de 60)" when it is 46 of 60. Prompt hardening and
injected authoritative facts both failed to stop this — the model ignores
numbers it already has in front of it. This module enforces grounding
*deterministically*: it recomputes per-agent ground truth from the simulation
events and rewrites provably-wrong action-count claims in the prose to the true
values.

Scope is deliberately narrow and safe: it only rewrites "N de M" action/movement
counts attributed to a *single* agent, replacing fabricated numbers with the
true ones derived from the events. It never invents claims, never touches
multi-agent prose (whose counts are ambiguous), and never alters step references
like "paso 6 de 60".
"""

from __future__ import annotations

import json
import re
from collections import Counter

from simlab.environment import Event

MOVE_PREFIX = "move_"

# "N de M" — the shape every fabricated action-count claim took in the judged
# runs ("60 de 72", "58 de 60", "50 de 72").
_NUM_DE_NUM = re.compile(r"(\d+)\s+de\s+(\d+)")

# Words that mark a "N de M" as an action-count claim (vs. a step reference).
_ACTION_CTX = re.compile(r"movimiento|acciones|acci[oó]n", re.IGNORECASE)

# Per-direction breakdown the LLM sometimes lists ("12 right, 14 up, 16 down,
# 8 left") next to a fabricated bare total ("52 movimientos"). Summing the
# breakdown gives an internal cross-check.
_DIR = r"(?:right|left|up|down|derecha|izquierda|arriba|abajo)"
_DIR_COUNT = re.compile(rf"(\d+)\s*{_DIR}", re.IGNORECASE)
_MOV_TOTAL = re.compile(r"(\d+)\s+movimientos", re.IGNORECASE)


def agent_action_facts(events: list[Event]) -> dict[str, dict]:
    """Recompute per-agent action ground truth from the raw events.

    One action per step, so ``total`` == steps survived. ``moves`` is the sum of
    every ``move_*`` action.
    """
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    facts: dict[str, dict] = {}
    for agent_id, evs in by_agent.items():
        counts = Counter(e.action.name for e in evs)
        facts[agent_id] = {
            "total": len(evs),
            "moves": sum(c for n, c in counts.items() if n.startswith(MOVE_PREFIX)),
            "stay": counts.get("stay", 0),
            "eat": counts.get("eat", 0),
            "counts": dict(counts),
        }
    return facts


def _facts_for(name: str, facts: dict[str, dict]) -> dict | None:
    """Resolve a prose agent label to its facts, tolerating ``model/formulation``
    keying on either side (the Tracker keys trajectories by the suffix)."""
    if name in facts:
        return facts[name]
    suffix = name.split("/")[-1]
    if suffix in facts:
        return facts[suffix]
    for key, rec in facts.items():
        if key.split("/")[-1] in (name, suffix):
            return rec
    return None


def _lint_n_de_m(text: str, rec: dict) -> tuple[str, list[str]]:
    """Rewrite fabricated "N de M" action counts in ``text`` to ground truth."""
    corrections: list[str] = []
    moves, total = rec["moves"], rec["total"]

    def repl(m: re.Match) -> str:
        n, big = int(m.group(1)), int(m.group(2))
        before = text[max(0, m.start() - 40) : m.start()]
        after = text[m.end() : m.end() + 22]
        # Only act on genuine action-count claims — leave "paso 6 de 60" alone.
        if not (_ACTION_CTX.search(before) or _ACTION_CTX.search(after)):
            return m.group(0)
        # Movement context anywhere adjacent → the pair is (moves, total).
        if _ACTION_CTX.search(before) and "movimiento" in (before + after).lower():
            n_true, big_true = moves, total
        else:
            n_true, big_true = n, total  # at least pin the (fabricated) total
        if (n, big) == (n_true, big_true):
            return m.group(0)
        corrections.append(f"'{m.group(0)}' -> '{n_true} de {big_true}'")
        return f"{n_true} de {big_true}"

    return _NUM_DE_NUM.sub(repl, text), corrections


def _lint_movement_breakdown(text: str, rec: dict) -> tuple[str, list[str]]:
    """Fix a bare "N movimientos" total against its own per-direction breakdown.

    Only fires when the prose lists >=2 direction counts AND their sum equals the
    agent's true movement count — so the rewrite is guaranteed correct, not a
    guess. Caught CASO2's "52 movimientos (12 right, 14 up, 16 down, 8 left)"
    where the truth (and the breakdown) is 50.
    """
    dir_counts = [int(n) for n in _DIR_COUNT.findall(text)]
    if len(dir_counts) < 2 or sum(dir_counts) != rec["moves"]:
        return text, []
    true_moves = rec["moves"]
    first_dir = _DIR_COUNT.search(text)
    breakdown_start = first_dir.start() if first_dir else len(text)
    corrections: list[str] = []

    def repl(m: re.Match) -> str:
        stated = int(m.group(1))
        # Only the total adjacent to (just before) the breakdown — never a
        # windowed "13 movimientos en 24 pasos" elsewhere in the field.
        if not (0 <= breakdown_start - m.end() <= 80) or stated == true_moves:
            return m.group(0)
        corrections.append(f"'{m.group(0)}' -> '{true_moves} movimientos'")
        return f"{true_moves} movimientos"

    return _MOV_TOTAL.sub(repl, text), corrections


def _lint_counts(text: str, rec: dict) -> tuple[str, list[str]]:
    """Run every count-grounding rule over one prose field."""
    text, c1 = _lint_n_de_m(text, rec)
    text, c2 = _lint_movement_breakdown(text, rec)
    return text, c1 + c2


def _lint_record_fields(
    record: dict, fields: tuple[str, ...], rec: dict, label: str
) -> list[str]:
    corrections: list[str] = []
    for field in fields:
        value = record.get(field)
        if isinstance(value, str):
            new, corr = _lint_counts(value, rec)
            if corr:
                record[field] = new
                corrections += [f"{label}.{field}: {c}" for c in corr]
    return corrections


def lint_tracker_output(
    tracker_json: str, events: list[Event]
) -> tuple[str, list[str]]:
    """Correct fabricated action counts in the Tracker's episode prose."""
    facts = agent_action_facts(events)
    try:
        data = json.loads(tracker_json)
    except (json.JSONDecodeError, TypeError):
        return tracker_json, []

    corrections: list[str] = []
    for ep in data.get("episodes", []) or []:
        if not isinstance(ep, dict):
            continue
        rec = _facts_for(str(ep.get("agent", "")), facts)
        if rec is None:
            continue
        corrections += _lint_record_fields(
            ep, ("description",), rec, f"episode[{ep.get('agent')}]"
        )

    if not corrections:
        return tracker_json, []
    return json.dumps(data, ensure_ascii=False, indent=2), corrections


def lint_analyst_output(
    analyst_json: str, events: list[Event]
) -> tuple[str, list[str]]:
    """Correct fabricated action counts in single-agent Analyst pattern prose.

    Multi-agent patterns are skipped: with two agents in scope, "(58 de 60)" is
    ambiguous and we never guess whose count it is.
    """
    facts = agent_action_facts(events)
    try:
        data = json.loads(analyst_json)
    except (json.JSONDecodeError, TypeError):
        return analyst_json, []

    corrections: list[str] = []
    for p in data.get("patterns", []) or []:
        if not isinstance(p, dict):
            continue
        agents = p.get("agents") or []
        if len(agents) != 1:
            continue
        rec = _facts_for(str(agents[0]), facts)
        if rec is None:
            continue
        corrections += _lint_record_fields(
            p, ("description", "evidence"), rec, f"pattern[{p.get('id', '?')}]"
        )

    if not corrections:
        return analyst_json, []
    return json.dumps(data, ensure_ascii=False, indent=2), corrections
