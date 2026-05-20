#!/usr/bin/env python3
"""Generate the Phase 2 architecture Excalidraw diagram."""

import json
import uuid

elements = []

def uid():
    return uuid.uuid4().hex[:16]

def rect(x, y, w, h, stroke="#6c6f85", bg="#transparent", fill="solid", sw=2, rough=0, opacity=100, radius=8):
    rid = uid()
    elements.append({
        "id": rid, "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": fill, "strokeWidth": sw, "roughness": rough,
        "opacity": opacity, "angle": 0, "groupIds": [],
        "roundness": {"type": 3, "value": radius},
        "boundElements": [], "locked": False,
        "updated": 1, "link": None,
    })
    return rid

def text(x, y, w, h, txt, size=20, color="#e6e6e6", family=1, align="center", valign="middle", container=None, bold=False):
    tid = uid()
    el = {
        "id": tid, "type": "text",
        "x": x, "y": y, "width": w, "height": h,
        "text": txt, "originalText": txt,
        "fontSize": size, "fontFamily": family,
        "textAlign": align, "verticalAlign": valign,
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "roughness": 0,
        "opacity": 100, "angle": 0, "groupIds": [],
        "roundness": None, "boundElements": [],
        "locked": False, "updated": 1, "link": None,
        "autoResize": True, "lineHeight": 1.25,
    }
    if container:
        el["containerId"] = container
    elements.append(el)
    return tid

def box_with_label(x, y, w, h, label, stroke="#6c6f85", bg="#7c3aed", text_color="#e6e6e6", font_size=18):
    """Rectangle with centered text inside."""
    rid = rect(x, y, w, h, stroke=stroke, bg=bg)
    tid = text(x + 10, y + h//2 - font_size//2, w - 20, font_size + 6, label,
               size=font_size, color=text_color, container=rid)
    # link them
    for el in elements:
        if el["id"] == rid:
            el["boundElements"].append({"id": tid, "type": "text"})
    return rid

def arrow(x1, y1, x2, y2, color="#a6adc8", sw=2, label=None, start_id=None, end_id=None):
    aid = uid()
    dx = x2 - x1
    dy = y2 - y1
    el = {
        "id": aid, "type": "arrow",
        "x": x1, "y": y1, "width": abs(dx), "height": abs(dy),
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": sw, "roughness": 0,
        "opacity": 100, "angle": 0, "groupIds": [],
        "roundness": {"type": 2},
        "boundElements": [],
        "points": [[0, 0], [dx, dy]],
        "startArrowhead": None, "endArrowhead": "arrow",
        "locked": False, "updated": 1, "link": None,
    }
    if start_id:
        el["startBinding"] = {"elementId": start_id, "focus": 0, "gap": 4}
    if end_id:
        el["endBinding"] = {"elementId": end_id, "focus": 0, "gap": 4}
    elements.append(el)

    if label:
        mid_x = x1 + dx // 2
        mid_y = y1 + dy // 2
        text(mid_x - 60, mid_y - 16, 120, 20, label, size=13, color=color, align="center")

    return aid

def group_box(x, y, w, h, label, stroke="#585b70", bg="#313244", label_color="#cdd6f4", opacity=40):
    """Large grouping rectangle with label at top-left."""
    rid = rect(x, y, w, h, stroke=stroke, bg=bg, opacity=opacity, sw=1)
    text(x + 15, y + 8, len(label) * 11, 22, label, size=16, color=label_color, bold=True)
    return rid

# ──────────────────────────────────────────────────────────────────────
# Title
# ──────────────────────────────────────────────────────────────────────
text(440, 15, 720, 40, "SimLab — Virtual Lab Architecture", size=32, color="#cdd6f4")

# ──────────────────────────────────────────────────────────────────────
# USER INTERFACE
# ──────────────────────────────────────────────────────────────────────
group_box(500, 70, 600, 100, "USER INTERFACE", stroke="#7f849c", bg="#45475a", label_color="#bac2de")

cli_id = box_with_label(540, 100, 220, 50, "CLI (Typer)", bg="#585b70", stroke="#7f849c", text_color="#cdd6f4")
web_id = box_with_label(840, 100, 220, 50, "Web UI (React + Vite)", bg="#585b70", stroke="#7f849c", text_color="#cdd6f4", font_size=15)

# ──────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────
orch_id = box_with_label(530, 210, 540, 65, "ORCHESTRATOR  (claude-sonnet-4-5)", bg="#1e66f5", stroke="#89b4fa", text_color="#ffffff", font_size=20)

# arrows user → orchestrator
arrow(650, 150, 700, 210, color="#a6adc8", start_id=cli_id, end_id=orch_id)
arrow(950, 150, 900, 210, color="#a6adc8", start_id=web_id, end_id=orch_id)

# ──────────────────────────────────────────────────────────────────────
# WebSocket API (between orchestrator and web)
# ──────────────────────────────────────────────────────────────────────
text(1075, 130, 160, 18, "WebSocket /ws", size=13, color="#89b4fa")
text(1075, 148, 200, 18, "(FastAPI → real-time)", size=11, color="#7f849c")

# ──────────────────────────────────────────────────────────────────────
# PIPELINE AGENTS
# ──────────────────────────────────────────────────────────────────────
agents_group = group_box(50, 310, 1500, 130, "PIPELINE AGENTS", stroke="#7c3aed", bg="#2e1065", label_color="#c4b5fd")

# Agent colors: purple
agent_bg = "#7c3aed"
agent_stroke = "#a78bfa"
agent_text = "#ffffff"

arch_id = box_with_label(80, 355, 260, 60, "Architect", bg=agent_bg, stroke=agent_stroke, text_color=agent_text)
track_id = box_with_label(370, 355, 260, 60, "Tracker", bg=agent_bg, stroke=agent_stroke, text_color=agent_text)
analyst_id = box_with_label(660, 355, 260, 60, "Analyst", bg=agent_bg, stroke=agent_stroke, text_color=agent_text)
reporter_id = box_with_label(950, 355, 260, 60, "Reporter", bg=agent_bg, stroke=agent_stroke, text_color=agent_text)
# NL-SQL is an Orchestrator-side tool (query_history), not a pipeline agent — kept in this row but visually flagged as such
nlsql_id = box_with_label(1240, 355, 260, 60, "NL-SQL  (Orch tool: query_history)", bg="#6c3483", stroke="#a78bfa", text_color=agent_text, font_size=13)

# model labels under each agent
text(80, 420, 260, 16, "claude-haiku-4-5", size=11, color="#a78bfa")
text(370, 420, 260, 16, "claude-sonnet-4-5", size=11, color="#a78bfa")
text(660, 420, 260, 16, "claude-sonnet-4-5", size=11, color="#a78bfa")
text(950, 420, 260, 16, "claude-haiku-4-5", size=11, color="#a78bfa")
text(1240, 420, 260, 16, "claude-haiku-4-5", size=11, color="#a78bfa")

# Orchestrator → agents arrows
for agent_id, ax in [(arch_id, 210), (track_id, 500), (analyst_id, 790), (reporter_id, 1080), (nlsql_id, 1370)]:
    arrow(800, 275, ax, 355, color="#89b4fa", sw=1, start_id=orch_id, end_id=agent_id)

# ──────────────────────────────────────────────────────────────────────
# SIMULATION ENGINE (left)
# ──────────────────────────────────────────────────────────────────────
sim_group = group_box(50, 480, 560, 280, "SIMULATION ENGINE", stroke="#e6a817", bg="#3d2800", label_color="#f9e2af")

env_id = box_with_label(80, 520, 500, 50, "Environment (Grid + Actions + Resources)",
                        bg="#b87a00", stroke="#f9e2af", text_color="#1e1e2e", font_size=15)
loader_id = box_with_label(80, 585, 500, 50, "Model Loader (Postgres → S3 → importlib → duck typing)",
                           bg="#b87a00", stroke="#f9e2af", text_color="#1e1e2e", font_size=13)
crit_id = box_with_label(80, 650, 500, 50, "Critical Events (rule-based detector)",
                         bg="#b87a00", stroke="#f9e2af", text_color="#1e1e2e", font_size=15)
charts_id = box_with_label(80, 715, 500, 50, "Charts (matplotlib + Recharts JSON)",
                           bg="#b87a00", stroke="#f9e2af", text_color="#1e1e2e", font_size=15)

# Architect → Environment
arrow(210, 415, 210, 520, color="#f9e2af", label="JSON spec", start_id=arch_id, end_id=env_id)

# Environment → Tracker (events)
arrow(580, 545, 500, 420, color="#f9e2af", label="events")

# ──────────────────────────────────────────────────────────────────────
# KNOWLEDGE LAYER (right)
# ──────────────────────────────────────────────────────────────────────
kg_group = group_box(660, 480, 890, 280, "KNOWLEDGE LAYER", stroke="#04b575", bg="#002b1a", label_color="#a6e3a1")

# sim-memory (write)
mem_group = group_box(685, 515, 400, 225, "sim-memory (write path)", stroke="#f38ba8", bg="#3b1528", label_color="#f38ba8", opacity=50)
box_with_label(710, 550, 350, 40, "TrackerMemoryWriter", bg="#a6325a", stroke="#f38ba8", text_color="#ffffff", font_size=14)
box_with_label(710, 600, 350, 40, "FactSpec → embed (Voyage-3)", bg="#a6325a", stroke="#f38ba8", text_color="#ffffff", font_size=14)
box_with_label(710, 650, 350, 40, "Upsert (Qdrant + Postgres)", bg="#a6325a", stroke="#f38ba8", text_color="#ffffff", font_size=14)
box_with_label(710, 700, 350, 40, "Sparse: BM25 native (Qdrant)", bg="#a6325a", stroke="#f38ba8", text_color="#ffffff", font_size=14)

# sim-recall (read) — Phase 2 wrapper. The actual 3-layer pipeline lives in Phase 1.
recall_group = group_box(1110, 515, 415, 225, "sim-recall (read path)", stroke="#74c7ec", bg="#0b2942", label_color="#74c7ec", opacity=50)
box_with_label(1135, 550, 365, 40, "retrieve_context  (P2 wrapper)", bg="#1a6694", stroke="#74c7ec", text_color="#ffffff", font_size=13)
box_with_label(1135, 600, 365, 40, "delegates to Phase 1:", bg="#1a6694", stroke="#74c7ec", text_color="#ffffff", font_size=13)
box_with_label(1135, 650, 365, 40, "  create_retrieve_knowledge()", bg="#1a6694", stroke="#74c7ec", text_color="#ffffff", font_size=13)
box_with_label(1135, 700, 365, 40, "  → 3-layer + RRF + CRAG (P1)", bg="#1a6694", stroke="#74c7ec", text_color="#ffffff", font_size=13)
# Note: chat_history (recall/chat_history.py) persists Orchestrator messages to chat_messages

# Tracker → sim-memory arrow
arrow(500, 420, 885, 515, color="#f38ba8", sw=2, label="write facts", start_id=track_id)

# sim-recall → Architect, Analyst, Reporter (dashed-style arrows)
arrow(1317, 550, 1080, 420, color="#74c7ec", sw=1, label="retrieve_context")
arrow(1317, 550, 790, 420, color="#74c7ec", sw=1)
arrow(1317, 550, 210, 420, color="#74c7ec", sw=1)

# ──────────────────────────────────────────────────────────────────────
# STORAGE LAYER (bottom)
# ──────────────────────────────────────────────────────────────────────
storage_group = group_box(50, 800, 1500, 170, "STORAGE LAYER", stroke="#04b575", bg="#002b1a", label_color="#a6e3a1")

# PostgreSQL
pg_id = box_with_label(80, 845, 320, 100,
    "PostgreSQL\n─────────\nexperiments / models / runs\nsimulation_observations (P2)\npipeline_memories (P1)\nnode_run_observations",
    bg="#166534", stroke="#a6e3a1", text_color="#e6e6e6", font_size=12)

# MinIO / S3
s3_id = box_with_label(430, 845, 320, 100,
    "MinIO / S3\n─────────\nevents.json\nreplay.json\ntracker / analyst\nPDF reports\nmodel .py files",
    bg="#166534", stroke="#a6e3a1", text_color="#e6e6e6", font_size=13)

# Qdrant
qd_id = box_with_label(780, 845, 320, 100,
    "Qdrant\n─────────\nmemories_dense (1024d)\nmemories_sparse (BM25 IDF)\n\nP1+P2 share, source_kind tag",
    bg="#166534", stroke="#a6e3a1", text_color="#e6e6e6", font_size=12)

# Neo4j
neo_id = box_with_label(1130, 845, 320, 100,
    "Neo4j\n─────────\nEntities / Relations\nProvenance (run_ids)\nTemporal edges\nNative vector index",
    bg="#166534", stroke="#a6e3a1", text_color="#e6e6e6", font_size=12)

# ──────────────────────────────────────────────────────────────────────
# Arrows: agents/engine → storage
# ──────────────────────────────────────────────────────────────────────

# Simulation engine → S3 (events, replay)
arrow(330, 765, 590, 845, color="#f9e2af", sw=1, label="write artifacts")

# Simulation engine → Postgres (experiments)
arrow(200, 765, 240, 845, color="#f9e2af", sw=1)

# sim-memory → Qdrant
arrow(885, 740, 940, 845, color="#f38ba8", sw=1, label="embeddings")

# sim-memory → Postgres (simulation_observations)
arrow(885, 740, 240, 845, color="#f38ba8", sw=1, label="typed obs rows")

# sim-recall → Neo4j (Cypher)
arrow(1317, 740, 1290, 845, color="#74c7ec", sw=1, label="Cypher + PPR")

# sim-recall → Qdrant (ANN search)
arrow(1317, 740, 940, 845, color="#74c7ec", sw=1, label="ANN search")

# Reporter → S3 (PDF)
arrow(1080, 420, 590, 845, color="#cba6f7", sw=1, label="PDF")

# NL-SQL → Postgres
arrow(1370, 420, 240, 845, color="#cba6f7", sw=1, label="SQL queries")

# ──────────────────────────────────────────────────────────────────────
# Annotations
# ──────────────────────────────────────────────────────────────────────
text(50, 970, 500, 16, "Knowledge infra optional (ENABLE_KNOWLEDGE_READ/WRITE)", size=12, color="#7f849c", align="left")
text(50, 988, 500, 16, "All LLM calls via OpenRouter → Anthropic models", size=12, color="#7f849c", align="left")

# Pipeline flow annotation
text(80, 445, 600, 16, "Pipeline: Architect → Simulate → Tracker → Analyst → Reporter", size=12, color="#cba6f7", align="left")

# Phase 1 integration note — model_loader reads Postgres models table first, then downloads .py from S3
text(80, 770, 600, 16, "Phase 1 models registered in Postgres (models table) → loaded via duck typing from S3", size=11, color="#f9e2af", align="left")
# chat_history note — added in P3 (recall/chat_history.py)
text(50, 1006, 600, 16, "Orchestrator messages persisted via recall/chat_history.py → chat_messages table", size=12, color="#7f849c", align="left")

# ──────────────────────────────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────────────────────────────
diagram = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {
        "viewBackgroundColor": "#1e1e2e",
        "gridSize": None,
        "theme": "dark",
    },
    "files": {},
}

out_path = "architecture.excalidraw"
with open(out_path, "w") as f:
    json.dump(diagram, f, indent=2)
print(f"Written {len(elements)} elements to {out_path}")
