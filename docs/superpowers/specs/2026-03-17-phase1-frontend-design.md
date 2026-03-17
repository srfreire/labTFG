# Phase 1 Frontend — Design Spec

## Goal

Replace the Phase 1 CLI entirely with a web UI that lets the user launch, monitor, and interact with the full agent pipeline (Research → Formalize → Reason → Build) through an interactive graph visualization. Follows Juan's Phase 2 visual style (terminal/cyberpunk dark aesthetic).

The CLI (`cli.py`, `feedback.py`, `questionary` dependency) remains in the codebase but is no longer the primary interface. The web UI is the sole user-facing interface going forward. Both CLI and web share the same `Router` — the Router dispatches to different feedback implementations depending on context.

## Architecture

```
phase1-pablo/
├── web/                              # Frontend
│   └── src/
│       ├── App.tsx                   # Sidebar + MainPanel layout
│       ├── hooks/useWebSocket.ts     # WS communication
│       ├── components/
│       │   ├── Sidebar.tsx           # Pipeline stages + controls
│       │   ├── Graph.tsx             # React Flow graph
│       │   ├── nodes/               # Custom graph nodes
│       │   └── reviews/             # Review stage panels
│       └── types.ts
└── src/decisionlab/
    ├── server.py                     # NEW: FastAPI + WebSocket
    └── ...                           # Existing code, Router adapted
```

### Tech Stack (mirrors Phase 2)

- React 19 + Vite + Tailwind v4 + TypeScript
- IBM Plex Mono, black background, rgba opacity layers
- Additional: `@xyflow/react`, `lucide-react`, `react-markdown`, `remark-math`, `remark-gfm`, `rehype-katex`, `react-syntax-highlighter`, `elkjs`

### Data Flow

1. User opens web → WebSocket connects to FastAPI
2. User types problem + clicks Run → `{type: "start", problem: "..."}`
3. Backend runs `Router.run()` in asyncio task, emits graph events via WS
4. Frontend builds graph in real-time from events
5. At review stages: backend pauses, emits `review_request`, waits for `review_response`
6. User interacts with review UI, sends response, pipeline continues

## Layout

**Sidebar** (fixed left, ~280px):
- Header: "DecisionLab" + "Pipeline" + WS connection dot
- Stage list (vertical) — display names map to `Stage` enum values:
  - RESEARCH (`RESEARCH`)
  - REVIEW (`REVIEW_RESEARCH`) — indented
  - FORMALIZE (`FORMALIZE`)
  - REVIEW (`REVIEW_FORMALIZE`) — indented
  - ENV SPEC (`GET_ENV_SPEC`)
  - REASON (`REASON`)
  - REVIEW (`REVIEW_REASON`) — indented
  - BUILD (`BUILD`)
  - REVIEW (`REVIEW_BUILD`) — indented
  - Dot per stage: grey=pending, amber+pulse=active, green=done, red=error
  - Click completed stage → view cached results in MainPanel (read-only graph snapshot + rendered output)
- Bottom: input + "RUN" button (idle) or "CANCEL" button (running)

**MainPanel** (fills remaining space): interactive graph or review panel.

## Graph Visualization (MainPanel — Agent Running)

Real-time directed graph built as the pipeline executes. Uses React Flow + ELK auto-layout.

### Node Types

| Type | Shape | Size | Icon (Lucide) | Behavior |
|------|-------|------|---------------|----------|
| Agent | Circle | Large | `Bot` | Pulse animation when active |
| Sub-agent | Circle | Medium | `Bot` (smaller) | Spawns from parent agent |
| Tool | Rounded rect | Small | Varies by tool | Appears on invocation |
| File | Rect + file icon | Small | `FileText` / `FilePlus` | Shows filename |
| Search | Rect + search icon | Small | `Search` | Shows query text |

**Tool icons**: `web_search` → `Search`, `read_file` → `FileText`, `write_file` → `FilePlus`, `run_tests` → `FlaskConical`, `launch_deep_research` → `Microscope`

**Agent colors**: Researcher=blue(`#4a9eff`), Formalizer=purple(`#9b59b6`), Reasoner=orange(`#ff6b4a`), Builder=amber(`#fbbf24`)

### Edges

Directed arrows: Agent→Tool, Tool→File, Tool→Search, Agent→Sub-agent

### Behavior

- New nodes: scale-in animation. New edges: progressive draw.
- Active nodes pulse, completed nodes dim slightly.
- Auto-layout via ELK layered algorithm. Zoom + pan.
- **Layout strategy**: batch layout updates — re-layout on stage transitions or after a burst of nodes settles (debounce ~500ms), not on every single `node_add`. This prevents disorienting jumps during rapid tool-call sequences.

### Interaction

- Click Agent/Sub-agent → tooltip/panel with current output/reasoning (from `meta.output`)
- Click File → rendered content (from `meta.content`: markdown/LaTeX/code with highlighting)
- Click Search → search results (from `meta.query` + `meta.results`)
- Click Tool → arguments used (from `meta.args`)

### `node_add` meta contents by kind

| Kind | meta fields |
|------|-------------|
| agent | `{output?: string}` — accumulated reasoning/output text |
| sub_agent | `{output?: string, paradigm?: string}` |
| tool | `{args: Record<string, any>}` — tool call arguments |
| file | `{path: string, content?: string}` — file path + content (populated on click via lazy fetch) |
| search | `{query: string, results?: string[]}` — search query + result snippets |

## Review Stages (MainPanel — Review Active)

Graph pauses (agent node shows "waiting for review"). A **drawer panel** slides in from the right (~50% width), pushing the graph to the left (graph remains visible and interactive but compressed). Drawer has a semi-transparent `#090909` background with left border.

### Review Research

- List of paradigm cards: title + summary (paradigms identified by filesystem slug, e.g. `homeostatic-regulation`)
- Checkbox per paradigm to approve/reject
- Click card → expand full markdown content (rendered)
- "Continuar" button submits selection (disabled if nothing selected — at least 1 paradigm required)

### Review Formalize

- Grouped by paradigm (accordions)
- Within each: formulation cards with LaTeX rendered
- Checkbox per formulation
- "Continuar" button

### Get Env Spec (placeholder)

- Drag & drop file upload OR paste JSON textarea
- JSON preview
- "Continuar" button
- Future: auto-populated from Phase 2 integration (stage skipped entirely)

### Review Reason

- Spec cards: structured view of variables, parameters, rules, decision logic
- Per spec: "Aprobar" button or "Rechazar" + feedback textarea
- "Continuar" when all decided

### Review Build

- Per model: Python code (syntax highlighted) + test results (pass/fail with output)
- Errors shown inline
- "Aprobar" or feedback textarea (routed through routing LLM)
- When feedback triggers a rerun: backend emits `{type: "rerun", target: "reasoner"|"formalizer"|..., paradigm: "slug", reason: "..."}` so the frontend shows what's being re-run and why. Graph clears stale nodes for affected stages via `{type: "graph_clear", from_stage: "REASON"}`.
- "Continuar"

## WebSocket Protocol

### Frontend → Backend

```jsonc
{type: "start", problem: "survival decision-making"}
{type: "review_response", stage: "REVIEW_RESEARCH", data: {approved: ["slug1", "slug2"]}}
{type: "review_response", stage: "REVIEW_FORMALIZE", data: {selected: {"paradigm": ["form1", "form2"]}}}
{type: "review_response", stage: "GET_ENV_SPEC", data: {env_spec: {/*...*/}}}
{type: "review_response", stage: "REVIEW_REASON", data: {decisions: {"spec_id": {approved: true/false, feedback: "..."}}}}
{type: "review_response", stage: "REVIEW_BUILD", data: {decisions: {"slug": {approved: true/false, feedback: "..."}}}}
{type: "cancel"}
```

### Backend → Frontend

```jsonc
{type: "stage_change", stage: "RESEARCH", status: "running"|"done"|"error"}
{type: "node_add", node: {id, kind: "agent"|"sub_agent"|"tool"|"file"|"search", label, parent_id, meta: {args?, content?, query?, results?}}}
{type: "edge_add", edge: {source, target}}
{type: "node_update", id, status: "running"|"done"|"error"}
{type: "review_request", stage: "REVIEW_RESEARCH", data: {paradigms: [...]}}
{type: "rerun", target: "researcher"|"formalizer"|"reasoner"|"builder", paradigm: "slug", reason: "..."}
{type: "graph_clear", from_stage: "REASON"|"FORMALIZE"|...}  // clears stale nodes on rerun
{type: "pipeline_done"}
{type: "error", message: "..."}
```

## Backend Adaptation

- New `server.py`: FastAPI app + WebSocket endpoint + Vite proxy config
- `Router.run()` receives `emit(msg)` callback for WS events
- Each agent emits `node_add`/`edge_add` on tool calls, file creation, sub-agent spawns
- Review stages emit `review_request`, pause on `asyncio.Event`, resume on `review_response`
- `feedback.py` functions replaced by WS-based equivalents (new `web_feedback.py` that implements same interface but communicates via WS events + `asyncio.Event` instead of `questionary`)
- Cancel handling: `{type: "cancel"}` cancels the running `asyncio.Task`, pipeline state persists to disk at current stage. Frontend resets to idle.
- Single concurrent WS client supported. If a second tab connects, the first is disconnected.
- WS reconnection: frontend auto-reconnects with exponential backoff. If pipeline was in a review stage, backend re-emits the `review_request` on reconnect. If pipeline was mid-agent, frontend receives current graph state via a `{type: "state_sync", nodes: [...], edges: [...], stage: "..."}` catchup message.

## Component Structure

```
web/src/
├── App.tsx
├── index.css                        # Tailwind + fonts + scrollbar + keyframe animations
├── types.ts                         # GraphNode, GraphEdge, StageStatus, ReviewData, WSMessage
├── hooks/
│   └── useWebSocket.ts
├── components/
│   ├── Sidebar.tsx
│   ├── Graph.tsx                    # React Flow + ELK layout
│   ├── nodes/
│   │   ├── AgentNode.tsx
│   │   ├── SubAgentNode.tsx
│   │   ├── ToolNode.tsx
│   │   ├── FileNode.tsx
│   │   └── SearchNode.tsx
│   ├── reviews/
│   │   ├── ReviewResearch.tsx
│   │   ├── ReviewFormalize.tsx
│   │   ├── EnvSpecUpload.tsx
│   │   ├── ReviewReason.tsx
│   │   └── ReviewBuild.tsx
│   └── shared/
│       ├── MarkdownRenderer.tsx     # react-markdown + remark-math + rehype-katex
│       └── CodeBlock.tsx            # react-syntax-highlighter, dark theme
```

## Visual Style

Identical to Phase 2:
- Background: `#000`, surfaces: `#090909`
- Font: IBM Plex Mono (300-600), all monospace
- Text: white with rgba opacity layers (0.15–1.0) for hierarchy
- Borders: `rgba(255,255,255, 0.1–0.3)`
- Text size: 7–14px range, uppercase with letter-spacing
- No rounded corners on panels — flat terminal aesthetic
- Scrollbar: 6px, black track, `#333` thumb
- Agent colors carry into graph node colors
