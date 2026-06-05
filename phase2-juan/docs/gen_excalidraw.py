#!/usr/bin/env python3
"""Phase 2 architecture — minimalist + technical.

Rules:
  - Title at TOP of every box. Content as separate text below. Never bind
    multi-line content to a container (Excalidraw clips it).
  - Arrows go vertical or short-diagonal only. No diagonal labels in the
    middle of empty space — labels sit just above the arrow's midpoint.
  - Generous vertical spacing between layers so labels never collide.
  - Color encodes role; legend explains.
"""

import json
import uuid

elements = []


def uid():
    return uuid.uuid4().hex[:16]


def rect(x, y, w, h, stroke, bg, sw=2, radius=8):
    rid = uid()
    elements.append(
        {
            "id": rid,
            "type": "rectangle",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "strokeColor": stroke,
            "backgroundColor": bg,
            "fillStyle": "solid",
            "strokeWidth": sw,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "groupIds": [],
            "roundness": {"type": 3, "value": radius},
            "boundElements": [],
            "locked": False,
            "updated": 1,
            "link": None,
        }
    )
    return rid


def text(x, y, w, h, txt, size=14, color="#e6e6e6", align="left"):
    elements.append(
        {
            "id": uid(),
            "type": "text",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "text": txt,
            "originalText": txt,
            "fontSize": size,
            "fontFamily": 1,
            "textAlign": align,
            "verticalAlign": "top",
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "groupIds": [],
            "roundness": None,
            "boundElements": [],
            "locked": False,
            "updated": 1,
            "link": None,
            "autoResize": True,
            "lineHeight": 1.25,
        }
    )


def arrow(x1, y1, x2, y2, color="#a6adc8", sw=2):
    dx, dy = x2 - x1, y2 - y1
    elements.append(
        {
            "id": uid(),
            "type": "arrow",
            "x": x1,
            "y": y1,
            "width": abs(dx),
            "height": abs(dy),
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": sw,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "groupIds": [],
            "roundness": {"type": 2},
            "boundElements": [],
            "points": [[0, 0], [dx, dy]],
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "locked": False,
            "updated": 1,
            "link": None,
        }
    )


def simple_box(x, y, w, h, label, stroke, bg, color, size=16):
    rect(x, y, w, h, stroke=stroke, bg=bg)
    text(
        x,
        y + h // 2 - size // 2 - 2,
        w,
        size + 6,
        label,
        size=size,
        color=color,
        align="center",
    )


def agent_box(x, y, name, model):
    rect(x, y, 260, 74, stroke="#a78bfa", bg="#7c3aed")
    text(x, y + 10, 260, 22, name, size=16, color="#ffffff", align="center")
    text(x, y + 42, 260, 16, model, size=11, color="#ddd6fe", align="center")


def info_box(
    x,
    y,
    w,
    h,
    title,
    lines,
    stroke,
    bg,
    title_color,
    line_color,
    title_size=18,
    line_size=12,
    title_align="center",
):
    """Rectangle + title + left-aligned content lines, all unbound."""
    rect(x, y, w, h, stroke=stroke, bg=bg)
    text(
        x,
        y + 12,
        w,
        title_size + 4,
        title,
        size=title_size,
        color=title_color,
        align=title_align,
    )
    for i, line in enumerate(lines):
        text(
            x + 16,
            y + 16 + (title_size + 14) + i * (line_size + 6),
            w - 32,
            line_size + 6,
            line,
            size=line_size,
            color=line_color,
            align="left",
        )


# ── Palette ──────────────────────────────────────────────────────────
GREY = ("#7f849c", "#585b70")
BLUE_STROKE = "#89b4fa"
BLUE_BG = "#1e66f5"
AMBER_S, AMBER_B = "#f9e2af", "#b87a00"
GREEN_S, GREEN_B = "#a6e3a1", "#04b575"
STORE_S, STORE_B = "#a6e3a1", "#166534"

W_DATA = "#f9e2af"  # simulation data
W_WRITE = "#f38ba8"  # KG write
W_READ = "#74c7ec"  # KG read
W_PIPE = "#cba6f7"  # pipeline / delegation


# ── Title ────────────────────────────────────────────────────────────
text(
    360,
    20,
    760,
    40,
    "SimLab — Arquitectura de la Fase 2",
    size=28,
    color="#cdd6f4",
    align="center",
)

# ── User row (y=90) ──────────────────────────────────────────────────
simple_box(220, 90, 240, 50, "CLI (Typer)", *GREY, "#cdd6f4")
simple_box(1020, 90, 240, 50, "Web UI (React + Vite)", *GREY, "#cdd6f4", size=14)

# ── Orchestrator (y=210) ─────────────────────────────────────────────
simple_box(
    430,
    210,
    620,
    64,
    "Orchestrator  ·  chat + tool dispatch",
    BLUE_STROKE,
    BLUE_BG,
    "#ffffff",
    size=18,
)
text(
    430,
    282,
    620,
    14,
    "WebSocket /ws (FastAPI)   ·   tool query_history (NL→SQL → Postgres)",
    size=11,
    color=BLUE_STROKE,
    align="center",
)

# User → Orchestrator
arrow(340, 140, 600, 210, "#a6adc8")
arrow(1140, 140, 880, 210, "#a6adc8")

# ── Pipeline agents row (y=360) ──────────────────────────────────────
AY = 360
agent_box(80, AY, "Architect", "claude-haiku-4-5")
agent_box(400, AY, "Tracker", "claude-sonnet-4-5")
agent_box(720, AY, "Analyst", "claude-sonnet-4-5")
agent_box(1040, AY, "Reporter", "claude-haiku-4-5")

# Orchestrator → Architect (single delegation arrow)
arrow(740, 274, 210, AY, color=W_PIPE, sw=2)
text(
    420,
    296,
    280,
    16,
    "delega pipeline secuencial",
    size=11,
    color=W_PIPE,
    align="center",
)

# Horizontal pipeline between agents (y center = AY+37)
PIPE_Y = AY + 37
for x_from, x_to in [(340, 400), (660, 720), (980, 1040)]:
    arrow(x_from, PIPE_Y, x_to, PIPE_Y, color=W_PIPE, sw=2)

# ── Layer row (y=510) ────────────────────────────────────────────────
LY = 510
info_box(
    80,
    LY,
    600,
    150,
    "Simulation Engine",
    [
        "•  Environment  (grid + actions + resources)",
        "•  Model Loader  (Postgres → S3 → importlib, duck typing con Fase 1)",
        "•  Critical Events detector  +  Charts (matplotlib / Recharts)",
        "•  Eventos emitidos al Tracker (subscribe)",
    ],
    AMBER_S,
    AMBER_B,
    "#1e1e2e",
    "#1e1e2e",
)

info_box(
    720,
    LY,
    600,
    150,
    "Knowledge Backbone",
    [
        "•  Write (sim-memory):  TrackerMemoryWriter → Voyage-3 → Qdrant + Postgres",
        "•  Read·push (kg-enrichment):  Orchestrator prefetch_knowledge → '## Knowledge context'",
        "•  Read·pull (sim-recall):  agent tool retrieve_context — 3-layer KG · dense · BM25 · RRF · CRAG",
        "•  Consumers: Architect · Analyst · Reporter  ·  flags ENABLE_KNOWLEDGE_READ / WRITE",
    ],
    GREEN_S,
    GREEN_B,
    "#ffffff",
    "#e6e6e6",
)

# Architect → Sim Engine (vertical)
arrow(210, AY + 74, 210, LY, color=W_DATA, sw=2)
text(60, AY + 92, 140, 16, "JSON spec  →", size=11, color=W_DATA, align="right")

# Tracker → Knowledge write (short diagonal) — NEW: sim-memory
arrow(530, AY + 74, 820, LY, color=W_WRITE, sw=4)
text(610, AY + 78, 180, 16, "write facts", size=11, color=W_WRITE, align="center")

# Knowledge → Reporter read — covers both push (prefetch) and pull (tool) — NEW: kg-enrichment + sim-recall
arrow(1220, LY, 1170, AY + 74, color=W_READ, sw=4)
text(1230, AY + 86, 220, 16, "←  prefetch (push)", size=11, color=W_READ, align="left")
text(
    1230,
    AY + 102,
    220,
    16,
    "←  retrieve_context (pull)",
    size=11,
    color=W_READ,
    align="left",
)


# ── Storage row (y=700) ──────────────────────────────────────────────
SY = 700
STORE_BOXES = [
    (
        80,
        "PostgreSQL",
        [
            "experiments · models · runs",
            "chat_messages",
            "simulation_observations",
            "pipeline_memories",
        ],
    ),
    (
        400,
        "MinIO (S3)",
        [
            "events.json · replay.json",
            "tracker · analyst dumps",
            "PDF reports",
            "modelos .py (Fase 1)",
        ],
    ),
    (
        720,
        "Qdrant",
        [
            "memories_dense (1024d, Voyage-3)",
            "memories_sparse (BM25 nativo)",
            "shared P1 + P2 (source_kind)",
        ],
    ),
    (
        1040,
        "Neo4j",
        [
            "Entities / Relations",
            "Provenance (run_ids)",
            "Temporal edges",
            "Native vector index",
        ],
    ),
]
for x, name, desc_lines in STORE_BOXES:
    info_box(
        x,
        SY,
        260,
        130,
        name,
        desc_lines,
        STORE_S,
        STORE_B,
        "#ffffff",
        "#e6e6e6",
        title_size=15,
        line_size=10,
    )

# Sim Engine → storage (Postgres + MinIO)
arrow(220, LY + 150, 220, SY, color=W_DATA, sw=1)
arrow(540, LY + 150, 540, SY, color=W_DATA, sw=1)
text(
    100,
    LY + 158,
    540,
    16,
    "artifacts (runs · events · PDFs)",
    size=11,
    color=W_DATA,
    align="center",
)

# Knowledge → storage (Qdrant + Neo4j)
arrow(860, LY + 150, 860, SY, color=W_READ, sw=1)
arrow(1180, LY + 150, 1180, SY, color=W_READ, sw=1)
text(
    800,
    LY + 158,
    540,
    16,
    "vectores + grafo de conocimiento",
    size=11,
    color=W_READ,
    align="center",
)

# ── Legend (y=850) ───────────────────────────────────────────────────
LGY = 850
text(
    80,
    LGY,
    1240,
    16,
    "Capas:   gris = interfaz   ·   azul = orquestador   ·   morado = agentes "
    "  ·   ámbar = motor de simulación   ·   verde = knowledge / storage",
    size=12,
    color="#9399b2",
    align="left",
)
text(
    80,
    LGY + 22,
    1240,
    16,
    "Flechas:   lavanda = delegación pipeline   ·   ámbar = datos de simulación "
    "  ·   rosa = write KG   ·   cyan = read KG",
    size=12,
    color="#9399b2",
    align="left",
)
text(
    80,
    LGY + 44,
    1240,
    16,
    "Integración Fase 1:   .py duck-typed (DecisionModel)   ·   "
    "Knowledge compartido vía source_kind tag en Qdrant",
    size=12,
    color="#9399b2",
    align="left",
)


# ── NEW since last tutor review ──────────────────────────────────────
NEW_COLOR = "#fbbf24"  # amber yellow
NEW_BG = "#3d2800"  # dark amber bg

# Numbered markers placed inline next to the relevant existing labels
MARKERS = ["①", "②", "③", "④"]


def new_marker(x, y, n):
    text(x, y, 22, 18, MARKERS[n - 1], size=15, color=NEW_COLOR, align="center")


# ①  sim-memory       — inline with "write facts" label
new_marker(584, 436, 1)

# ③  kg-enrichment    — inline with "← prefetch (push)" label
new_marker(1206, 444, 3)

# ②  sim-recall        — inline with "← retrieve_context (pull)" label
new_marker(1206, 462, 2)

# ④  nlsql              — at the end of Orchestrator subtitle, right of "query_history"
new_marker(1055, 282, 4)

# Panel at the bottom explaining each marker
PY = 925
rect(70, PY, 1260, 120, stroke=NEW_COLOR, bg=NEW_BG, sw=2)
text(
    86,
    PY + 12,
    1240,
    22,
    "Nuevo desde la última revisión del tutor",
    size=15,
    color=NEW_COLOR,
    align="left",
)
text(
    86,
    PY + 40,
    1240,
    16,
    "①   sim-memory        —   Tracker escribe observaciones tipadas al KG "
    "(Voyage-3 embed → Qdrant + Postgres, BM25 nativo)",
    size=12,
    color="#e6e6e6",
    align="left",
)
text(
    86,
    PY + 58,
    1240,
    16,
    "②   sim-recall          —   Agentes consultan KG vía retrieve_context (pull)   ·   "
    "chat_messages persistido entre sesiones   ·   query_history light path",
    size=12,
    color="#e6e6e6",
    align="left",
)
text(
    86,
    PY + 76,
    1240,
    16,
    "③   kg-enrichment    —   Orchestrator prefetch_knowledge inyecta "
    "'## Knowledge context' en los prompts de Architect/Analyst/Reporter (push)",
    size=12,
    color="#e6e6e6",
    align="left",
)
text(
    86,
    PY + 94,
    1240,
    16,
    "④   nlsql                  —   Tool Orchestrator-side: NL→SQL sobre experiments · "
    "models · simulation_observations · pipeline_memories · chat_messages",
    size=12,
    color="#e6e6e6",
    align="left",
)


# ── Output ───────────────────────────────────────────────────────────
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

with open("architecture.excalidraw", "w") as f:
    json.dump(diagram, f, indent=2)
print(f"Written {len(elements)} elements")
