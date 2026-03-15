# Phase 1 Integration + UI Polish — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Phase 1 Builder models into Phase 2 simulations and polish the Web UI with a simulation grid replay, richer data cards, responsive layout, and animations.

**Architecture:** Backend gets a model loader module + orchestrator changes. Frontend gets a new SimulationGrid component, improved data cards, and visual polish. ReplayData is built server-side from environment snapshots and sent via WebSocket.

**Tech Stack:** Python 3 / FastAPI / importlib, React 19 / TypeScript / Tailwind CSS v4

**Spec:** `docs/superpowers/specs/2026-03-16-phase1-integration-ui-polish-design.md`

---

## Chunk 1: Backend — Model Loader + Orchestrator

### Task 1: Create model_loader.py

**Files:**
- Create: `phase2-juan/simlab/model_loader.py`
- Create: `phase2-juan/tests/test_model_loader.py`
- Reference: `phase1-pablo/examples/sample-run/builder/homeostatic-regulation_drive_reduction_rl_model.py`

- [ ] **Step 1: Write test for discover_models**

```python
# phase2-juan/tests/test_model_loader.py
"""Tests for dynamic model discovery and loading."""
from pathlib import Path
from simlab.model_loader import discover_models, load_model

BUILDER_DIR = Path(__file__).resolve().parent.parent.parent / "phase1-pablo" / "examples" / "sample-run" / "builder"


def test_discover_finds_both_models():
    models = discover_models(BUILDER_DIR)
    assert len(models) >= 2
    assert "homeostatic-regulation_drive_reduction_rl" in models
    assert "homeostatic-regulation_pi_negative_feedback" in models


def test_model_info_has_required_fields():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_drive_reduction_rl"]
    assert info.formulation_id == "homeostatic-regulation_drive_reduction_rl"
    assert info.class_name == "HomeostaticDriveReductionRL"
    assert info.description  # non-empty docstring
    assert info.path.exists()
    assert info.model_class is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd phase2-juan && uv run pytest tests/test_model_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simlab.model_loader'`

- [ ] **Step 3: Implement discover_models**

```python
# phase2-juan/simlab/model_loader.py
"""Dynamic loader for Phase 1 Builder decision models."""
from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    formulation_id: str
    class_name: str
    description: str
    path: Path
    model_class: type


def _has_decision_model_interface(cls: type) -> bool:
    return (
        callable(getattr(cls, "decide", None))
        and callable(getattr(cls, "update", None))
        and callable(getattr(cls, "get_state", None))
    )


def discover_models(builder_dir: Path) -> dict[str, ModelInfo]:
    """Scan builder_dir for *_model.py files and return discovered models."""
    models: dict[str, ModelInfo] = {}
    for path in sorted(builder_dir.glob("*_model.py")):
        formulation_id = path.stem.removesuffix("_model")
        module_name = f"_builder_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)

            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if obj.__module__ == module_name and _has_decision_model_interface(obj):
                    models[formulation_id] = ModelInfo(
                        formulation_id=formulation_id,
                        class_name=name,
                        description=(mod.__doc__ or "").strip(),
                        path=path,
                        model_class=obj,
                    )
                    break
        except Exception:
            logger.warning("Failed to load model from %s", path, exc_info=True)
    return models
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd phase2-juan && uv run pytest tests/test_model_loader.py::test_discover_finds_both_models tests/test_model_loader.py::test_model_info_has_required_fields -v`
Expected: PASS

- [ ] **Step 5: Write test for load_model**

Add to `phase2-juan/tests/test_model_loader.py`:

```python
def test_load_model_returns_decision_model():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    model = load_model(info)
    assert hasattr(model, "decide")
    assert hasattr(model, "update")
    assert hasattr(model, "get_state")
    state = model.get_state()
    assert isinstance(state, dict)
    assert "energy" in state


def test_load_model_with_kwargs():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    model = load_model(info, energy_set_point=90.0)
    assert model.s == 90.0


def test_load_model_with_seed():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_drive_reduction_rl"]
    m1 = load_model(info, seed=42)
    m2 = load_model(info, seed=42)
    perception = {"x": 5, "y": 5, "grid_width": 10, "grid_height": 10, "step": 0,
                  "resources": {"food": [{"x": 6, "y": 5, "type": "food", "palatability": 0.8}]},
                  "last_action_result": {}}
    a1 = m1.decide(perception)
    a2 = m2.decide(perception)
    assert a1.name == a2.name


def test_load_model_bad_kwargs_raises():
    models = discover_models(BUILDER_DIR)
    info = models["homeostatic-regulation_pi_negative_feedback"]
    try:
        load_model(info, nonexistent_param=999)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_discover_skips_bad_files(tmp_path):
    bad_file = tmp_path / "broken_model.py"
    bad_file.write_text("raise SyntaxError('nope')")
    models = discover_models(tmp_path)
    assert len(models) == 0
```

- [ ] **Step 6: Implement load_model**

Add to `phase2-juan/simlab/model_loader.py`:

```python
import random


def load_model(model_info: ModelInfo, *, seed: int | None = None, **kwargs) -> object:
    """Instantiate a discovered model with optional parameter overrides."""
    if seed is not None:
        random.seed(seed)
    try:
        return model_info.model_class(**kwargs)
    except TypeError as e:
        raise ValueError(f"Failed to instantiate {model_info.class_name}: {e}") from e
```

- [ ] **Step 7: Run all model_loader tests**

Run: `cd phase2-juan && uv run pytest tests/test_model_loader.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add phase2-juan/simlab/model_loader.py phase2-juan/tests/test_model_loader.py
git commit -m "feat[phase2]: add dynamic model loader for Phase 1 Builder models"
```

---

### Task 2: Add list_available_models tool to Orchestrator

**Files:**
- Modify: `phase2-juan/simlab/orchestrator.py`

- [ ] **Step 1: Add builder_dir to Orchestrator.__init__**

In `orchestrator.py`, modify the `__init__` signature to accept `builder_dir: Path | None = None` and store it as `self.builder_dir`.

```python
# Add to __init__ params:
builder_dir: Path | None = None,

# Add in body:
self.builder_dir = builder_dir
```

- [ ] **Step 2: Add LIST_AVAILABLE_MODELS_TOOL schema**

Add after the existing tool schemas (before `ALL_TOOLS`):

```python
LIST_AVAILABLE_MODELS_TOOL = {
    "name": "list_available_models",
    "description": "List available decision models that can be used in simulations. Call this before run_simulation to let the user choose a model.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}
```

Add to `ALL_TOOLS` list: `LIST_AVAILABLE_MODELS_TOOL,`

- [ ] **Step 3: Add model_id parameter to RUN_SIMULATION_TOOL**

Add to `RUN_SIMULATION_TOOL["input_schema"]["properties"]`:

```python
"model_id": {"type": "string", "description": "Formulation ID of the model to use (from list_available_models). If omitted, uses a simple built-in model."},
```

- [ ] **Step 4: Implement list_available_models tool function**

Add inside `_build_tools()`:

```python
async def list_available_models(params: dict) -> str:
    if not self.builder_dir or not self.builder_dir.exists():
        return json.dumps({"models": [], "note": "No builder directory configured"})
    from simlab.model_loader import discover_models
    models = discover_models(self.builder_dir)
    return json.dumps({
        "models": [
            {"formulation_id": m.formulation_id, "class_name": m.class_name, "description": m.description}
            for m in models.values()
        ]
    })
```

Add `"list_available_models": list_available_models,` to the registry dict.

- [ ] **Step 5: Rewrite run_simulation with model loading + replay capture**

Replace the entire `run_simulation` closure inside `_build_tools()` with this version that handles both model loading AND per-step replay frame capture (combining what would otherwise be two separate edits):

```python
        async def run_simulation(params: dict) -> str:
            if not state.get("spec"):
                return json.dumps({"error": "No environment created yet. Call create_environment first."})
            env = spec_to_environment(state["spec"], seed=params.get("seed"))
            num_agents = params["num_agents"]
            steps = params["steps"]
            rng = random.Random(params.get("seed"))
            action_names = [a["name"] for a in state["spec"]["actions"]]

            # Load model if model_id provided
            model_id = params.get("model_id")
            model_info = None
            if model_id and self.builder_dir:
                from simlab.model_loader import discover_models, load_model
                available = discover_models(self.builder_dir)
                model_info = available.get(model_id)

            for i in range(num_agents):
                if model_info:
                    model = load_model(model_info, seed=rng.randint(0, 2**32))
                elif i < len(self.decision_models):
                    model = self.decision_models[i]
                else:
                    model = _DummyModel(action_names, random.Random(rng.randint(0, 2**32)))
                pos = Position(rng.randint(0, env.width - 1), rng.randint(0, env.height - 1))
                env.add_agent(Agent(id=f"agent_{i}", position=pos, decision_model=model))

            # Run step-by-step, capturing replay frames
            all_events = []
            replay_frames = []
            for _ in range(steps):
                if env.is_finished():
                    break
                env_state = env.get_state()
                step_events = env.step()
                all_events.extend(step_events)
                replay_frames.append({
                    "step": env_state["step"],
                    "agents": env_state["agents"],
                    "resources": [
                        {"type": r.get("type", "unknown"), "x": r["x"], "y": r["y"]}
                        for r in env_state["resources"]
                    ],
                    "actions": [
                        {"agent_id": e.agent_id, "action": e.action.name, "reward": e.outcome.get("reward", 0)}
                        for e in step_events
                    ],
                })

            state["events"] = all_events
            state["replay"] = {
                "grid_width": env.width,
                "grid_height": env.height,
                "total_steps": len(replay_frames),
                "frames": replay_frames,
            }
            state["tracker_output"] = None
            state["analyst_output"] = None

            summary = {
                "agents": num_agents,
                "steps": steps,
                "total_events": len(all_events),
                "agents_alive": sum(1 for a in env._agents if a.alive),
                "model": model_id or "dummy",
            }
            return json.dumps(summary)
```

- [ ] **Step 6: Update system prompt to mention model selection**

Add to `ORCHESTRATOR_SYSTEM_PROMPT` before the pipeline order section:

```python
## Model selection

Before running a simulation, call list_available_models to check what decision models are available. \
Present the options to the user and let them choose. Then pass the chosen model_id to run_simulation. \
If no models are available, use the built-in dummy model and tell the user.
```

- [ ] **Step 7: Commit**

```bash
git add phase2-juan/simlab/orchestrator.py
git commit -m "feat[phase2]: add model discovery + selection to Orchestrator"
```

---

### Task 3: Wire ReplayData through API + clean up

**Files:**
- Modify: `phase2-juan/simlab/api.py`

Note: ReplayData capture was already added to `run_simulation` in Task 2 Step 5. This task only touches `api.py`.

- [ ] **Step 1: Clean up api.py dead wrapper code**

In `api.py`, **delete** the entire `patched_build` block — everything from `original_build = orch._build_tools` through `return tools, registry  # Use original for now`. This is dead code that was never called. The existing `response = await orch.chat(user_text)` line (immediately after the block) should remain.

- [ ] **Step 2: Add replay data to WebSocket response in api.py**

In the response-building section, after the `analyst` attachment block and **before** `await ws.send_json(response_data)`, add:

```python
                if state.get("replay"):
                    response_data["replay"] = state["replay"]
```

- [ ] **Step 3: Pass builder_dir to Orchestrator in api.py**

Add `BUILDER_DIR` constant after the existing `OUTPUT_DIR` line and pass it to the Orchestrator constructor:

```python
BUILDER_DIR = RESEARCH_DIR / "builder"
```

In the `websocket_chat` handler, update Orchestrator construction:

```python
    orch = Orchestrator(
        client=client,
        research_dir=RESEARCH_DIR,
        output_dir=OUTPUT_DIR,
        builder_dir=BUILDER_DIR,
    )
```

- [ ] **Step 4: Enhance spec card with model info**

In the spec card section of `api.py` (the `if state.get("spec") and not state.get("events"):` block), add model name to the card data:

```python
                if state.get("spec") and not state.get("events"):
                    response_data["card"] = {
                        "title": "Environment Spec",
                        "data": {
                            "Grid": f"{state['spec']['grid']['width']} × {state['spec']['grid']['height']}",
                            "Acciones": str(len(state["spec"]["actions"])),
                            "Recursos": ", ".join(f"{r['type']} ×{r['count']}" for r in state["spec"]["resources"]),
                        },
                    }
```

Also add a card after simulation that includes model info — after the `replay` attachment:

```python
                if state.get("events") and state.get("replay"):
                    sim_summary = {
                        "title": "Simulación completada",
                        "data": {
                            "Steps": str(state["replay"]["total_steps"]),
                            "Agentes": str(len(state["replay"]["frames"][0]["agents"]) if state["replay"]["frames"] else 0),
                        },
                    }
                    if not response_data.get("card"):
                        response_data["card"] = sim_summary
```

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/simlab/api.py
git commit -m "feat[phase2]: wire ReplayData through API + clean up dead code"
```

---

## Chunk 2: Frontend — Types, SimulationGrid, Data Cards, Polish

### Task 4: Add ReplayData types and wire through WebSocket hook

**Files:**
- Modify: `phase2-juan/web/src/types.ts`
- Modify: `phase2-juan/web/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Add ReplayData types**

Add to `types.ts`:

```typescript
export interface ReplayFrame {
  step: number
  agents: { id: string; x: number; y: number; alive: boolean }[]
  resources: { type: string; x: number; y: number }[]
  actions: { agent_id: string; action: string; reward: number }[]
}

export interface ReplayData {
  grid_width: number
  grid_height: number
  total_steps: number
  frames: ReplayFrame[]
}
```

Add `replay?: ReplayData` to `ChatMessage` interface.

- [ ] **Step 2: Wire replay in useWebSocket**

In `useWebSocket.ts`, in the `'message'` case, add `replay: data.replay,` to the message object.

- [ ] **Step 3: Commit**

```bash
git add phase2-juan/web/src/types.ts phase2-juan/web/src/hooks/useWebSocket.ts
git commit -m "feat[phase2]: add ReplayData types + wire through WebSocket hook"
```

---

### Task 5: Create SimulationGrid component

**Files:**
- Create: `phase2-juan/web/src/components/SimulationGrid.tsx`
- Modify: `phase2-juan/web/src/components/ChatPanel.tsx`

- [ ] **Step 1: Create SimulationGrid.tsx**

```tsx
// phase2-juan/web/src/components/SimulationGrid.tsx
import { useState, useEffect, useRef, useCallback } from 'react'
import type { ReplayData } from '../types'

interface Props {
  replay: ReplayData
}

const AGENT_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c']
const SPEEDS = [0.5, 1, 2, 4]

export function SimulationGrid({ replay }: Props) {
  const [currentStep, setCurrentStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [trail, setTrail] = useState<Record<string, { x: number; y: number }[]>>({})
  const intervalRef = useRef<number | null>(null)
  const TRAIL_LENGTH = 5

  const frame = replay.frames[currentStep]
  const speed = SPEEDS[speedIdx]

  // Build trail history
  useEffect(() => {
    if (!frame) return
    setTrail(prev => {
      const next = { ...prev }
      for (const agent of frame.agents) {
        const history = next[agent.id] || []
        next[agent.id] = [...history.slice(-(TRAIL_LENGTH - 1)), { x: agent.x, y: agent.y }]
      }
      return next
    })
  }, [currentStep, frame])

  // Playback interval
  useEffect(() => {
    if (playing) {
      intervalRef.current = window.setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= replay.total_steps - 1) {
            setPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 200 / speed)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, speed, replay.total_steps])

  const togglePlay = useCallback(() => setPlaying(p => !p), [])
  const stepBack = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.max(0, s - 1)) }, [])
  const stepForward = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.min(replay.total_steps - 1, s + 1)) }, [replay.total_steps])
  const reset = useCallback(() => { setPlaying(false); setCurrentStep(0); setTrail({}) }, [])
  const cycleSpeed = useCallback(() => setSpeedIdx(i => (i + 1) % SPEEDS.length), [])

  if (!frame) return null

  const cellSize = Math.min(28, Math.floor(300 / Math.max(replay.grid_width, replay.grid_height)))

  return (
    <div className="mt-3 border p-3" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-[1px]" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Simulación
        </span>
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
          Step {currentStep + 1} / {replay.total_steps}
        </span>
      </div>

      {/* Grid */}
      <div
        className="mx-auto"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${replay.grid_width}, ${cellSize}px)`,
          gridTemplateRows: `repeat(${replay.grid_height}, ${cellSize}px)`,
          gap: '1px',
          width: 'fit-content',
        }}
      >
        {Array.from({ length: replay.grid_height }, (_, y) =>
          Array.from({ length: replay.grid_width }, (_, x) => {
            const resource = frame.resources.find(r => r.x === x && r.y === y)
            const agent = frame.agents.find(a => a.x === x && a.y === y && a.alive)
            const agentIdx = agent ? frame.agents.findIndex(a => a.id === agent.id) : -1
            const isTrail = !agent && Object.entries(trail).some(([id, positions]) => {
              const a = frame.agents.find(a2 => a2.id === id)
              if (a && a.x === x && a.y === y) return false
              return positions.some(p => p.x === x && p.y === y)
            })

            return (
              <div
                key={`${x}-${y}`}
                style={{
                  width: cellSize,
                  height: cellSize,
                  background: 'rgba(255,255,255,0.02)',
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {resource && !agent && (
                  <div style={{
                    width: cellSize * 0.3,
                    height: cellSize * 0.3,
                    borderRadius: '50%',
                    background: '#22c55e',
                    opacity: 0.6,
                  }} />
                )}
                {agent && (
                  <div style={{
                    width: cellSize * 0.65,
                    height: cellSize * 0.65,
                    borderRadius: '50%',
                    background: AGENT_COLORS[agentIdx % AGENT_COLORS.length],
                    transition: 'all 150ms ease-out',
                    boxShadow: `0 0 ${cellSize * 0.4}px ${AGENT_COLORS[agentIdx % AGENT_COLORS.length]}40`,
                  }} />
                )}
                {isTrail && (
                  <div style={{
                    width: cellSize * 0.2,
                    height: cellSize * 0.2,
                    borderRadius: '50%',
                    background: 'rgba(255,255,255,0.08)',
                  }} />
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-3 mt-2">
        <button onClick={reset} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>⟳</button>
        <button onClick={stepBack} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>◁</button>
        <button onClick={togglePlay} className="text-[9px] px-2.5 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.25)', color: 'rgba(255,255,255,0.6)' }}>
          {playing ? '⏸' : '▶'}
        </button>
        <button onClick={stepForward} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>▷</button>
        <button onClick={cycleSpeed} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>
          {speed}×
        </button>
      </div>

      {/* Step actions summary */}
      {frame.actions.length > 0 && (
        <div className="mt-2 flex gap-2 justify-center flex-wrap">
          {frame.actions.map((a, i) => (
            <span key={i} className="text-[8px] px-1.5 py-0.5 border" style={{
              borderColor: 'rgba(255,255,255,0.08)',
              color: a.reward > 0 ? '#4ade80' : 'rgba(255,255,255,0.3)',
            }}>
              {a.agent_id}: {a.action}{a.reward > 0 ? ` +${a.reward.toFixed(1)}` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Integrate SimulationGrid in ChatPanel**

In `ChatPanel.tsx`, import and render:

```tsx
import { SimulationGrid } from './SimulationGrid'
```

Inside `MessageBubble`, after the tracker card block and before the closing `</div>` of the message content, add:

```tsx
        {/* Simulation replay */}
        {msg.replay && (
          <SimulationGrid replay={msg.replay} />
        )}
```

- [ ] **Step 3: Commit**

```bash
git add phase2-juan/web/src/components/SimulationGrid.tsx phase2-juan/web/src/components/ChatPanel.tsx
git commit -m "feat[phase2]: add SimulationGrid replay component"
```

---

### Task 6: Improve data cards (Tracker + Analyst)

**Files:**
- Modify: `phase2-juan/web/src/components/ChatPanel.tsx`

- [ ] **Step 1: Enhance tracker card**

Replace the existing tracker card block in `MessageBubble` with:

```tsx
        {/* Tracker data */}
        {msg.tracker && (
          <div className="mt-3 border p-2.5 animate-card-in" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: '#fbbf24' }}>
              Trayectorias
            </div>
            {Object.entries(msg.tracker.trajectories).map(([agent, data]) => (
              <div key={agent} className="mb-2 p-2 border" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-[10px] font-semibold" style={{ color: 'rgba(255,255,255,0.6)' }}>{agent}</span>
                  <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{data.steps_survived} steps</span>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <span className="text-[8px] px-1.5 py-0.5 border" style={{ borderColor: 'rgba(255,255,255,0.08)', color: '#4ade80' }}>
                    🍎 {data.resources_consumed}
                  </span>
                  {Object.entries(data.actions).map(([action, count]) => (
                    <span key={action} className="text-[8px] px-1.5 py-0.5 border" style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.4)' }}>
                      {action}: {count}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
```

- [ ] **Step 2: Add analyst card**

After the tracker card and before the SimulationGrid, add:

```tsx
        {/* Analyst data */}
        {msg.analyst && (
          <div className="mt-3 border p-2.5 animate-card-in" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)', animationDelay: '100ms' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: '#a78bfa' }}>
              Análisis
            </div>
            {/* Patterns */}
            {msg.analyst.patterns.length > 0 && (
              <div className="mb-2">
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Patrones</div>
                {msg.analyst.patterns.map(p => (
                  <div key={p.id} className="flex items-start gap-1.5 py-1 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                    <span className="text-[8px] px-1 py-0.5 flex-shrink-0" style={{
                      background: p.type === 'anomaly' ? 'rgba(239,68,68,0.15)' : 'rgba(168,139,250,0.15)',
                      color: p.type === 'anomaly' ? '#ef4444' : '#a78bfa',
                      border: `1px solid ${p.type === 'anomaly' ? 'rgba(239,68,68,0.2)' : 'rgba(168,139,250,0.2)'}`,
                    }}>{p.type}</span>
                    <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{p.description}</span>
                  </div>
                ))}
              </div>
            )}
            {/* Comparisons */}
            {msg.analyst.comparisons.length > 0 && (
              <div className="mb-2">
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Comparaciones</div>
                {msg.analyst.comparisons.map((c, i) => (
                  <div key={i} className="py-1.5 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                    <div className="flex gap-2 mb-0.5">
                      <span className="text-[8px]" style={{ color: 'rgba(255,255,255,0.4)' }}>{c.metric}</span>
                      {Object.entries(c.values).map(([agent, val]) => (
                        <span key={agent} className="text-[9px] font-semibold">{agent}: {typeof val === 'number' ? val.toFixed(1) : val}</span>
                      ))}
                    </div>
                    <div className="text-[8px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{c.insight}</div>
                  </div>
                ))}
              </div>
            )}
            {/* Metrics */}
            {Object.keys(msg.analyst.metrics).length > 0 && (
              <div>
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Métricas</div>
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(msg.analyst.metrics).map(([agent, metrics]) => (
                    Object.entries(metrics).map(([key, val]) => (
                      <div key={`${agent}-${key}`} className="px-1.5 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                        <div className="text-[7px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{agent} · {key}</div>
                        <div className="text-[11px] font-semibold mt-0.5">{typeof val === 'number' ? val.toFixed(2) : val}</div>
                      </div>
                    ))
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
```

- [ ] **Step 3: Commit**

```bash
git add phase2-juan/web/src/components/ChatPanel.tsx
git commit -m "feat[phase2]: improve tracker card + add analyst card"
```

---

### Task 7: Animations, responsive layout, and CSS polish

**Files:**
- Modify: `phase2-juan/web/src/index.css`
- Modify: `phase2-juan/web/src/App.tsx`
- Modify: `phase2-juan/web/src/components/AgentPanel.tsx`
- Modify: `phase2-juan/web/src/components/ChatPanel.tsx`

- [ ] **Step 1: Add animations to index.css**

Replace `phase2-juan/web/src/index.css` with:

```css
@import "tailwindcss";

@theme {
  --font-mono: 'IBM Plex Mono', 'SF Mono', 'Monaco', monospace;
}

body {
  margin: 0;
  padding: 0;
  font-family: 'IBM Plex Mono', 'SF Mono', 'Monaco', monospace;
  background: #000;
  color: #fff;
  overflow: hidden;
}

#root { height: 100vh; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #000; }
::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }

/* Card entrance animation */
@keyframes card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-card-in {
  animation: card-in 0.3s ease-out both;
}

/* Message entrance */
@keyframes msg-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.animate-msg-in {
  animation: msg-in 0.25s ease-out both;
}

/* Typing dots */
@keyframes typing-dot {
  0%, 60%, 100% { opacity: 0.2; }
  30% { opacity: 1; }
}

.typing-dots span {
  animation: typing-dot 1.4s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

/* Bob animation for working agents */
@keyframes bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

/* Ping animation for agent status */
@keyframes ping {
  0% { transform: scale(1); opacity: 0.4; }
  50% { transform: scale(1.5); opacity: 0; }
  100% { transform: scale(1); opacity: 0; }
}

/* Pipeline step highlight */
@keyframes step-done {
  from { color: rgba(255,255,255,0.15); }
  to { color: rgba(255,255,255,0.6); }
}

.pipeline-step-done {
  animation: step-done 0.4s ease-out both;
}
```

- [ ] **Step 2: Add responsive layout to App.tsx**

Two targeted edits:

**Edit A:** Change the sidebar wrapper from `<div className="w-[340px] flex-shrink-0">` to:
```tsx
        <div className="hidden md:block w-[340px] flex-shrink-0">
```

**Edit B:** Add mobile agent bar before the closing `</div>` of the root flex-col container (after the `{/* Main */}` block):

```tsx
      {/* Mobile agent bar */}
      <div className="md:hidden flex items-center gap-2 px-4 py-2 border-t overflow-x-auto" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
        {agents.map(a => (
          <div key={a.name} className="flex items-center gap-1 flex-shrink-0">
            <div className="w-1.5 h-1.5 rounded-full" style={{
              background: a.color,
              opacity: a.status === 'idle' ? 0.3 : 1,
            }} />
            <span className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.4)' }}>{a.name}</span>
          </div>
        ))}
      </div>
```

- [ ] **Step 3: Add message animation to ChatPanel**

In `ChatPanel.tsx`, add `animate-msg-in` class to message wrapper:

```tsx
    <div className={`max-w-[85%] animate-msg-in ${isUser ? 'self-start' : 'self-end'}`}>
```

Replace the "Pensando..." indicator with typing dots:

```tsx
            <div className="px-3.5 py-2.5 border text-[11px] typing-dots" style={{ borderColor: 'rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.02)', color: 'rgba(255,255,255,0.4)' }}>
              Pensando<span>.</span><span>.</span><span>.</span>
            </div>
```

- [ ] **Step 4: Add pipeline step animation to AgentPanel**

In `AgentPanel.tsx`, in the pipeline rendering section (the `{PIPELINE_ALL.map((step, i) => ...}` block), replace the inner `<span>` for each step:

Change:
```tsx
              className="text-[8px] uppercase tracking-[1px] px-1.5 py-1"
              style={{ color: doneSteps.has(step) ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.15)' }}
```

To:
```tsx
              className={`text-[8px] uppercase tracking-[1px] px-1.5 py-1 transition-colors duration-400 ${doneSteps.has(step) ? 'pipeline-step-done' : ''}`}
              style={{ color: doneSteps.has(step) ? undefined : 'rgba(255,255,255,0.15)' }}
```

- [ ] **Step 5: Commit**

```bash
git add phase2-juan/web/src/index.css phase2-juan/web/src/App.tsx phase2-juan/web/src/components/ChatPanel.tsx phase2-juan/web/src/components/AgentPanel.tsx
git commit -m "feat[phase2]: add animations, responsive layout, typing dots"
```

---

### Task 8: Update CLAUDE.md and commit

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md Next Steps**

Replace the Next Steps section to reflect completed work and remaining items:

```markdown
## Next Steps

- [ ] Test Web UI end-to-end with real Phase 1 models
- [ ] Real-time WebSocket streaming during simulation (not just post-hoc replay)
- [ ] More decision paradigms from Phase 1 (when Pablo adds them)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with current status + next steps"
```
