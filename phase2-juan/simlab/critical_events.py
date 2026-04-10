"""
Critical event detection — rule-based, runs after simulation.

Detects noteworthy moments in the simulation without LLM:
  - consumption: agent successfully eats a resource
  - starvation: agent energy drops below critical threshold
  - death: agent dies
  - energy_spike: large change in energy between steps
  - strategy_shift: agent switches dominant action pattern
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from simlab.environment import Event


@dataclass
class CriticalEvent:
    step: int
    agent_id: str
    type: str  # consumption, starvation, death, energy_spike, strategy_shift
    severity: float  # 0-1, higher = more critical
    description: str
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_consumption(events: list[Event]) -> list[CriticalEvent]:
    """Detect successful resource consumption."""
    result = []
    for e in events:
        if e.outcome.get("action_result", {}).get("consumed"):
            reward = e.outcome.get("reward", 0)
            rtype = e.outcome.get("action_result", {}).get("resource_type", "recurso")
            result.append(CriticalEvent(
                step=e.step, agent_id=e.agent_id, type="consumption",
                severity=min(1.0, reward / 2.0),
                description=f"{e.agent_id} consumió {rtype} (reward={reward})",
                data={"reward": reward, "resource_type": rtype},
            ))
    return result


def _detect_energy_events(events: list[Event], low_threshold: float = 20.0, spike_threshold: float = 15.0) -> list[CriticalEvent]:
    """Detect low energy (starvation risk) and energy spikes."""
    result = []
    # Group by agent, ordered by step
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    for agent_id, agent_events in by_agent.items():
        prev_energy = None
        for e in agent_events:
            energy = e.outcome.get("model_state", {}).get("energy")
            if energy is None:
                continue

            # Starvation: energy below threshold
            if energy < low_threshold:
                result.append(CriticalEvent(
                    step=e.step, agent_id=agent_id, type="starvation",
                    severity=max(0.3, 1.0 - energy / low_threshold),
                    description=f"{agent_id} energía crítica: {energy:.1f}",
                    data={"energy": energy},
                ))

            # Energy spike: big change from previous step
            if prev_energy is not None:
                delta = abs(energy - prev_energy)
                if delta >= spike_threshold:
                    direction = "subió" if energy > prev_energy else "bajó"
                    result.append(CriticalEvent(
                        step=e.step, agent_id=agent_id, type="energy_spike",
                        severity=min(1.0, delta / (spike_threshold * 3)),
                        description=f"{agent_id} energía {direction} {delta:.1f} ({prev_energy:.1f}→{energy:.1f})",
                        data={"delta": delta, "from": prev_energy, "to": energy},
                    ))
            prev_energy = energy
    return result


def _detect_strategy_shift(events: list[Event], window: int = 5) -> list[CriticalEvent]:
    """Detect when an agent's dominant action changes over a sliding window."""
    result = []
    by_agent: dict[str, list[Event]] = {}
    for e in events:
        by_agent.setdefault(e.agent_id, []).append(e)

    for agent_id, agent_events in by_agent.items():
        if len(agent_events) < window * 2:
            continue
        for i in range(window, len(agent_events) - window + 1):
            before_counter = Counter(e.action.name for e in agent_events[i - window:i])
            after_counter = Counter(e.action.name for e in agent_events[i:i + window])
            dominant_before = before_counter.most_common(1)[0][0]
            dominant_after = after_counter.most_common(1)[0][0]
            if dominant_before != dominant_after:
                freq_before = before_counter[dominant_before] / window
                freq_after = after_counter[dominant_after] / window
                # Only flag if both are clearly dominant (>50%)
                if freq_before > 0.5 and freq_after > 0.5:
                    result.append(CriticalEvent(
                        step=agent_events[i].step, agent_id=agent_id,
                        type="strategy_shift",
                        severity=0.6,
                        description=f"{agent_id} cambió de '{dominant_before}' a '{dominant_after}'",
                        data={"from_action": dominant_before, "to_action": dominant_after},
                    ))
    # Deduplicate: keep only one per agent per shift (first occurrence)
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for ce in result:
        key = (ce.agent_id, ce.data["from_action"], ce.data["to_action"])
        if key not in seen:
            seen.add(key)
            deduped.append(ce)
    return deduped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_critical_events(events: list[Event]) -> list[CriticalEvent]:
    """Run all detectors and return critical events sorted by step."""
    critical = []
    critical.extend(_detect_consumption(events))
    critical.extend(_detect_energy_events(events))
    critical.extend(_detect_strategy_shift(events))
    critical.sort(key=lambda ce: (ce.step, ce.agent_id))
    return critical


def critical_events_to_json(critical: list[CriticalEvent]) -> list[dict]:
    """Convert critical events to JSON-serializable dicts."""
    return [
        {
            "step": ce.step,
            "agent_id": ce.agent_id,
            "type": ce.type,
            "severity": round(ce.severity, 2),
            "description": ce.description,
            "data": ce.data,
        }
        for ce in critical
    ]
