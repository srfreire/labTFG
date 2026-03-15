# Phase 1 Integration + UI Polish — Design Spec

**Date**: 2026-03-16
**Author**: Juan Freire Alvarez
**Status**: Draft

## Goal

Two parallel workstreams:

1. **Integrate Phase 1 Builder models** into Phase 2 simulations so the Orchestrator can discover, present, and use real decision models instead of the `_DummyModel` fallback.
2. **Polish the Web UI** — simulation grid with animated agent replay, richer data cards, responsive layout, smoother transitions.

---

## 1. Dynamic Model Loader

### New file: `simlab/model_loader.py`

Scans `phase1-pablo/examples/sample-run/builder/*_model.py` and loads models dynamically.

```python
@dataclass
class ModelInfo:
    formulation_id: str   # e.g. "homeostatic-regulation_drive_reduction_rl"
    class_name: str       # e.g. "HomeostaticDriveReductionRL"
    description: str      # from module docstring
    path: Path            # absolute path to .py file
    model_class: type     # the loaded class itself

def discover_models(builder_dir: Path) -> dict[str, ModelInfo]
def load_model(model_info: ModelInfo, **kwargs) -> object  # DecisionModel-compatible
```

**Key decisions:**
- Uses `importlib.util.spec_from_file_location` (same approach as Pablo's tests, handles hyphens in filenames).
- Finds the DecisionModel class by inspecting module exports for classes with `decide`, `update`, `get_state` methods.
- No `ModelAdapter` needed — Pablo's models already use the same perception dict and structurally identical `Action(name, params)`. Duck typing is sufficient. Note: Phase 1 models define their own `Action` dataclass inline — this is a different class than Phase 2's `Action`, but structurally identical (`name: str, params: dict`). Duck typing works because neither side does `isinstance` checks on Action.
- `load_model` instantiates with optional `**kwargs` to override default parameters.
- **Error handling**: `discover_models` skips files that fail to import (logs a warning). `load_model` catches instantiation errors and raises a descriptive `ValueError`.
- **Seed support**: `load_model` accepts an optional `seed: int` parameter. If provided, calls `random.seed(seed)` before instantiation so models using `random` are deterministic.

---

## 2. Orchestrator — Model Selection Flow

### New tool: `list_available_models`

- No parameters.
- Calls `discover_models()` on the configured builder directory.
- Returns list of `{formulation_id, class_name, description}`.

### Modified tool: `run_simulation`

- New optional parameter: `model_id: str` (the `formulation_id`).
- Add `model_id` to `RUN_SIMULATION_TOOL["input_schema"]["properties"]` as optional string.
- Loads the model with `load_model()` using the discovered `ModelInfo`.
- Falls back to `_DummyModel` if `model_id` not provided (backwards compat).

### Orchestrator constructor change

- New parameter: `builder_dir: Path` — path to the builder output directory.
- `list_available_models` calls `discover_models(self.builder_dir)`.
- `api.py` passes `builder_dir` when constructing the Orchestrator.

### System prompt update

Add instruction: before running any simulation, call `list_available_models` and present options to the user. Wait for selection before proceeding.

### Conversation flow

```
User: "Quiero simular un agente homeostático"
Orchestrator: [calls list_available_models]
  → "Hay 2 modelos disponibles:
     1. homeostatic-regulation_drive_reduction_rl — Q-learning con drive reduction
     2. homeostatic-regulation_pi_negative_feedback — Controlador PI
     ¿Cuál quieres usar?"
User: "El de RL"
Orchestrator: [calls create_environment, then run_simulation with model_id]
```

---

## 3. Simulation Grid Component

### New component: `SimulationGrid.tsx`

A visual replay of simulation results, rendered as a panel below the chat when tracker data is available.

**Rendering approach:** CSS grid with `div` cells. For typical sizes (10×10, 20×20) this is simpler than canvas and allows CSS `transition` for smooth agent movement.

**Data source — `ReplayData`:**

The current Tracker output does NOT contain per-step positions. A new `ReplayData` structure is built from the raw `Event` list in `run_simulation` (backend side) and sent to the frontend alongside tracker/analyst data.

```typescript
interface ReplayData {
  grid_width: number;
  grid_height: number;
  total_steps: number;
  frames: ReplayFrame[];  // one per simulation step
}

interface ReplayFrame {
  step: number;
  agents: { id: string; x: number; y: number; alive: boolean }[];
  resources: { type: string; x: number; y: number }[];
  actions: { agent_id: string; action: string; reward: number }[];
}
```

**Backend extraction:** After `env.run()`, iterate the `Event` list to build frames. Each Event already contains `action` and `outcome.model_state`. Agent positions are available from the environment's step snapshots. The `run_simulation` tool stores `replay_data` in `self._state` alongside events.

**WebSocket protocol:** Add optional `replay` field to the response message:
```json
{"type": "message", "from": "orchestrator", "text": "...", "card": {...}, "tracker": {...}, "analyst": {...}, "replay": {...}}
```

**Frontend types:** Add `replay?: ReplayData` to `ChatMessage` in `types.ts`.

**Replay mechanism:**
- When replay data arrives, grid panel appears below the chat.
- Play/pause button, speed control (0.5×, 1×, 2×), step-by-step navigation.
- Interval-based playback (default 200ms/step) advances through frames.
- Agents rendered as colored dots/icons, resources as smaller dots.

**Visual design:**
- Dark background consistent with theme (`#000` / `rgba(255,255,255,0.05)` grid lines).
- Agent colors match the sidebar palette.
- Food resources shown as small green dots.
- Current step indicator and total steps counter.
- Trail effect: faint dots showing last N positions.

**No real-time WebSocket needed** — this is a post-hoc replay from completed simulation data.

---

## 4. Data Cards Improvements

### Spec card (exists, enhance)
- Show action rules with their effect types.
- Show resource rules with properties and counts.
- Show selected model name and its parameters.

### Tracker card (exists, enhance)
- Steps survived, resources consumed, total actions as prominent metrics.
- Action breakdown by type (mini horizontal bars or pill counters).
- Per-agent mini summary if multiple agents.

### Analyst card (currently commented out, activate)
- Patterns as a list with severity/confidence badges.
- Agent comparisons as a simple table.
- Key metrics highlighted with values.

### Card transitions
- Fade-in + slide-up on appearance (CSS `@keyframes`).
- Staggered entrance when multiple cards appear together.

---

## 5. Responsive Layout

- **Sidebar** (AgentPanel): collapses to horizontal bar on `< 768px`.
- **SimulationGrid**: scales proportionally, maintains aspect ratio.
- **ChatPanel**: fills available space, input stays fixed at bottom.
- **Data cards**: stack vertically on narrow screens.

---

## 6. Animation Polish

- Message bubbles: fade-in + slight slide-up on appearance.
- "Pensando..." indicator: replace `animate-pulse` with a typing-dots animation.
- Lab floor agents: reflect actual status from WebSocket (already partially implemented, just wire up properly).
- Pipeline steps: animated highlight transitions between steps.

---

## Cleanup

- **`api.py` dead code**: Remove the broken wrapper code (lines ~77-149) that attempted real-time agent status updates with failed async patterns. Replace with clean pass-through until real-time WebSocket is implemented in a future iteration.

---

## Out of Scope

- Real-time WebSocket streaming of agent states during simulation (future work).
- New backend endpoints beyond the model loader tools.
- Changes to Phase 1 code.
- ModelAdapter refactoring (keep it for potential future use but don't use it now).

---

## File Changes Summary

| File | Change |
|------|--------|
| `simlab/model_loader.py` | **New** — discover_models, load_model |
| `simlab/orchestrator.py` | Add list_available_models tool, modify run_simulation, add builder_dir param, build ReplayData from events |
| `simlab/api.py` | Pass builder_dir config to Orchestrator, send replay data in WS message, clean up dead wrapper code |
| `web/src/types.ts` | Add ReplayData, ReplayFrame interfaces; add replay field to ChatMessage |
| `web/src/components/SimulationGrid.tsx` | **New** — grid replay component with playback controls |
| `web/src/components/ChatPanel.tsx` | Integrate SimulationGrid panel, improve data cards, activate analyst card |
| `web/src/components/AgentPanel.tsx` | Responsive collapse, animation polish |
| `web/src/hooks/useWebSocket.ts` | Parse replay data from messages |
| `web/src/App.tsx` | Responsive layout adjustments |
| `web/src/index.css` | New animations, responsive breakpoints |
