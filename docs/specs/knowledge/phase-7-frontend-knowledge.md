# Phase 7: Frontend Knowledge Visualization

> Status: done | Created: 2026-05-11 | Last updated: 2026-05-11 (P7-001..P7-005 done)
> References: [general.md](general.md) | [phases.md](phases.md)

## Objective

Surface the Knowledge Backbone inside Phase 2's web UI: an interactive
graph explorer, a memories inspector, and a provenance drawer — so the
user (and the TFG defense) can *see* what the lab knows and where each
fact came from.

## Requirements

### R1 — Reuse Phase 1's stack

- Frontend uses **`@xyflow/react` + `d3-force`** (same as
  `phase1-pablo/web`). Patterns can be lifted from
  `phase1-pablo/web/src/components/Graph.tsx`.
- Backend queries the **shared Neo4j** via
  `decisionlab.knowledge` clients already imported by
  `simlab/recall/`. No HTTP proxy to Phase 1; same process.
- Memories come from the **`memories` table in Postgres** (already
  populated by sim-memory).

### R2 — Backend endpoints (Phase 2 `api.py`)

Three new endpoints under `/api/knowledge/...`:

#### `GET /api/knowledge/graph`

Returns the full KG snapshot:

```json
{
  "nodes": [{"id": str, "label": str, "props": {...}, "run_id": str|null}],
  "edges": [{"id": str, "source": str, "target": str, "type": str, "props": {...}}],
  "current_run_node_ids": [str]  // when ?run_id supplied
}
```

Query params:
- `run_id` (optional): highlight nodes touched by this run.
- `namespace` (optional): filter to `paradigm` / `formulation` / `model` /
  `simulation` / `meta`.

Mirrors Phase 1's `/api/kg/snapshot` shape but lives under
`/api/knowledge/...` to keep namespacing clear on Phase 2's API surface.

#### `GET /api/knowledge/memories`

Returns rows from `memories` table:

```json
{
  "items": [{"id": str, "content": str, "namespace": str, "run_id": str,
             "created_at": str, "memory_type": str, "source_stage": str}],
  "total": int,
  "page": int,
  "page_size": int
}
```

Query params:
- `namespace` (optional)
- `run_id` (optional)
- `since` (ISO timestamp, optional)
- `page` (default 1)
- `page_size` (default 50, max 200)

#### `GET /api/knowledge/provenance/{node_id}`

Given a Neo4j node `elementId`, return the chain of edges + nodes that
explain its origin:

```json
{
  "node": {"id": str, "label": str, "props": {...}},
  "trail": [
    {"edge": {"type": str, "props": {...}},
     "node": {"id": str, "label": str, "props": {...}}}
  ]
}
```

The trail walks "backwards" from the node toward source `Paper` nodes
(via `SUPPORTS`, `CONTRADICTS`, `DERIVES_FROM`, `AUTHORED`, `CITES`,
etc.). Depth-limited to keep payload bounded.

### R3 — Frontend: knowledge panel

- New component `KnowledgePanel.tsx` rendered as a **collapsible right
  drawer** in `App.tsx` (no routing). Toggled by a sidebar button.
- Three tabs: `Graph | Memories | Provenance`.
- `Graph` tab uses `@xyflow/react`. Nodes positioned by `d3-force`.
  Node color encodes label (Paradigm / Postulate / Paper / ...). When
  `run_id` filter is active, nodes in `current_run_node_ids` are
  highlighted with a glow.
- `Memories` tab is a table with filters (`namespace`, `run_id`,
  `since`), pagination, click-to-expand row → shows full `content`.
- `Provenance` tab is empty until a node is selected; then it shows the
  trail returned by `/api/knowledge/provenance/{id}`.
- Clicking a node in the `Graph` tab auto-switches to the `Provenance`
  tab and loads the trail.

### R4 — Failure & empty states

- If Neo4j is unavailable: each endpoint returns 503 with a clear
  message. Frontend shows a placeholder ("Knowledge Graph unavailable —
  is the backend running?").
- Empty memories / empty graph: friendly empty-state copy ("No
  knowledge stored yet. Run an experiment to start populating the
  graph.").

## Acceptance Criteria

- [x] AC1: `GET /api/knowledge/graph` returns valid JSON for a seeded
      Neo4j; with `?run_id=X` the response carries
      `current_run_node_ids` for that run.
- [x] AC2: `GET /api/knowledge/memories?namespace=paradigm` returns
      paginated rows scoped to that namespace.
- [x] AC3: `GET /api/knowledge/provenance/{node_id}` returns a non-empty
      `trail` for a node that has incoming `SUPPORTS` / `AUTHORED` edges.
- [x] AC4: All three endpoints return 503 when the Neo4j client is None
      or Postgres is unreachable.
- [x] AC5: The `KnowledgePanel` mounts in `App.tsx`, opens via a
      sidebar button, and renders an interactive graph populated from
      the backend.
- [x] AC6: Clicking a node selects it, switches to the `Provenance`
      tab, and the trail panel shows the fetched chain.
- [x] AC7: Memories tab filters (namespace, run_id) actually trim the
      result set.
- [x] AC8: Build + TypeScript pass with the new dependencies installed.

## Technical Notes

- Phase 1's `/api/kg/snapshot` (`phase1-pablo/src/decisionlab/server.py:440`)
  is the reference implementation for the graph endpoint. The Phase 2
  version is a re-implementation under `/api/knowledge/graph` so Phase 2's
  frontend has a single backend to talk to.
- `@xyflow/react`'s `<ReactFlow>` + custom node renderer is the pattern
  used in `phase1-pablo/web/src/components/Graph.tsx`. Lift the layout
  (d3-force with link/charge/center forces) verbatim.
- Pagination on memories: simple `OFFSET/LIMIT`; total count via a
  second `COUNT(*)` query gated by the same filters.
- Provenance walk: Cypher `MATCH path = (n)-[*1..4]->(end:Paper)
  WHERE elementId(n) = $id RETURN path` (bounded depth 4). Convert to
  the response shape on the Python side.
- KnowledgePanel is large enough to deserve its own folder
  (`web/src/components/knowledge/`) with `KnowledgePanel.tsx`,
  `GraphTab.tsx`, `MemoriesTab.tsx`, `ProvenanceTab.tsx`.

## Decisions

| Decisión | Elección | Rationale |
|---|---|---|
| Phase 2 querying KG | Direct Neo4j client (no HTTP proxy) | Already imports `decisionlab.knowledge`; one less service to keep alive. |
| Viz library | `@xyflow/react` + `d3-force` | Phase 1 already uses it; consistency + lift-and-shift patterns. |
| UI integration | Right-side collapsible drawer | Avoids router refactor; matches the chat-centric layout. |
| Cross-run "diff" | Highlight-by-run filter (not side-by-side compare) | 80% of value at 20% of cost; full diff is a future iteration. |
| Provenance trigger | Click on graph node only (v1) | Clicks from chat citations / report sections is a later iteration. |
| Pagination | OFFSET/LIMIT + total via COUNT(*) | Memories table is small; simple is fine. |
| Provenance walk depth | Bounded to 4 | Prevents pathological payloads on dense subgraphs. |
| Endpoint namespace | `/api/knowledge/...` | Clear separation from existing Phase 2 endpoints. |
