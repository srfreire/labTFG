# Phase 1 Frontend — Design Spec

## Goal

Replace the Phase 1 CLI entirely with a web UI that lets the user launch, monitor, and interact with the full agent pipeline (Research → Formalize → Reason → Build) through an interactive graph visualization. Follows Juan's Phase 2 visual style (terminal/cyberpunk dark aesthetic).

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
- Stage list (vertical): RESEARCH, REVIEW, FORMALIZE, REVIEW, ENV SPEC, REASON, REVIEW, BUILD, REVIEW
  - Dot per stage: grey=pending, amber+pulse=active, green=done, red=error
  - Review stages indented/subtle (sub-steps)
  - Click completed stage → view its results in MainPanel (read-only)
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

**Agent colors**: Researcher=blue, Formalizer=green, Reasoner=violet, Builder=orange

### Edges

Directed arrows: Agent→Tool, Tool→File, Tool→Search, Agent→Sub-agent

### Behavior

- New nodes: scale-in animation. New edges: progressive draw.
- Active nodes pulse, completed nodes dim slightly.
- Auto-layout via ELK layered algorithm. Zoom + pan.

### Interaction

- Click Agent/Sub-agent → tooltip/panel with current output/reasoning
- Click File → rendered content (markdown/LaTeX/code with highlighting)
- Click Search → search results

## Review Stages (MainPanel — Review Active)

Graph pauses (agent node shows "waiting for review"). A **drawer panel** slides over/beside the graph with structured review controls.

### Review Research

- List of paradigm cards: title + summary
- Checkbox per paradigm to approve/reject
- Click card → expand full markdown content (rendered)
- "Continuar" button submits selection

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
{type: "stage_change", stage: "RESEARCH", status: "running"}
{type: "node_add", node: {id: "...", kind: "agent"|"sub_agent"|"tool"|"file"|"search", label: "...", parent_id: "...", meta: {}}}
{type: "edge_add", edge: {source: "...", target: "..."}}
{type: "node_update", id: "...", status: "running"|"done"|"error"}
{type: "review_request", stage: "REVIEW_RESEARCH", data: {paradigms: [...]}}
{type: "pipeline_done"}
{type: "error", message: "..."}
```

## Backend Adaptation

- New `server.py`: FastAPI app + WebSocket endpoint + Vite proxy config
- `Router.run()` receives `emit(msg)` callback for WS events
- Each agent emits `node_add`/`edge_add` on tool calls, file creation, sub-agent spawns
- Review stages emit `review_request`, pause on `asyncio.Event`, resume on `review_response`
- `feedback.py` functions replaced by WS-based equivalents

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
