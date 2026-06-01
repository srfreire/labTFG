#!/usr/bin/env python3
"""Storage layer — 4 cards: PostgreSQL · MinIO · Qdrant · Neo4j.

Goal: explain what lives in each storage backend, with concrete schema
fragments and a tiny query example. Especially clear on Qdrant + Neo4j
which are less intuitive than relational + object stores.
"""

import json
import uuid

elements = []


def uid():
    return uuid.uuid4().hex[:16]


def rect(x, y, w, h, stroke, bg, sw=2, radius=8):
    elements.append({
        "id": uid(), "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": sw, "roughness": 0,
        "opacity": 100, "angle": 0, "groupIds": [],
        "roundness": {"type": 3, "value": radius},
        "boundElements": [], "locked": False,
        "updated": 1, "link": None,
    })


def text(x, y, w, h, txt, size=14, color="#e6e6e6", align="left"):
    elements.append({
        "id": uid(), "type": "text",
        "x": x, "y": y, "width": w, "height": h,
        "text": txt, "originalText": txt,
        "fontSize": size, "fontFamily": 1,
        "textAlign": align, "verticalAlign": "top",
        "strokeColor": color, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "roughness": 0,
        "opacity": 100, "angle": 0, "groupIds": [],
        "roundness": None, "boundElements": [],
        "locked": False, "updated": 1, "link": None,
        "autoResize": True, "lineHeight": 1.25,
    })


def card(x, y, w, h, stroke, bg):
    rect(x, y, w, h, stroke=stroke, bg=bg)


def code_box(x, y, w, h, lines):
    """Dark monospace-ish code block (uses default font)."""
    rect(x, y, w, h, stroke="#45475a", bg="#11111b", sw=1, radius=4)
    for i, line in enumerate(lines):
        text(x + 10, y + 6 + i * 14, w - 20, 14, line,
             size=10, color="#cdd6f4", align="left")


# ── Title ────────────────────────────────────────────────────────────
text(280, 16, 880, 38, "Capa de Almacenamiento — qué guarda cada base de datos",
     size=26, color="#cdd6f4", align="center")
text(280, 52, 880, 18,
     "Cuatro almacenes complementarios. Postgres y MinIO son la base "
     "(metadatos + blobs). Qdrant y Neo4j alimentan el Knowledge Backbone.",
     size=12, color="#9399b2", align="center")


# ╔════════════════════════════════════════════════════════════════════╗
# ║ POSTGRES (top-left)                                                ║
# ╚════════════════════════════════════════════════════════════════════╝
PX, PY = 60, 100
PW, PH = 660, 440
card(PX, PY, PW, PH, "#74c7ec", "#0b2942")

text(PX + 20, PY + 16, PW - 40, 24, "🗄  PostgreSQL",
     size=20, color="#74c7ec", align="left")
text(PX + 20, PY + 44, PW - 40, 16, "Base de datos relacional   ·   metadatos + punteros",
     size=12, color="#9399b2", align="left")

text(PX + 20, PY + 72, PW - 40, 16,
     "Qué guarda:  filas tipadas con columnas, foreign keys, índices. "
     "El 'qué' y el 'dónde'.",
     size=12, color="#cdd6f4", align="left")

# Tables
text(PX + 20, PY + 100, PW - 40, 18, "Tablas principales:",
     size=13, color="#89b4fa", align="left")
TABLES = [
    ("experiments",            "id · spec · models_used · steps · s3_*_key · status"),
    ("models",                 "id · name · paradigm · s3_model_key · created_at"),
    ("runs",                   "Fase 1: pipeline runs (problem · status · s3_prefix)"),
    ("artifacts",              "índice: s3_key → run_id / experiment_id + tipo"),
    ("chat_messages",          "Orchestrator chat (sim-recall P2)"),
    ("simulation_observations","observaciones tipadas (sim-memory)"),
    ("pipeline_memories",      "Fase 1: bi-temporal con valid_from/valid_to"),
    ("node_run_observations",  "provenance KG: qué run tocó qué nodo"),
]
for i, (name, desc) in enumerate(TABLES):
    y = PY + 124 + i * 22
    text(PX + 30, y, 220, 16, f"• {name}",
         size=12, color="#a6e3a1", align="left")
    text(PX + 220, y, PW - 240, 16, desc,
         size=11, color="#cdd6f4", align="left")

# Query example
EX_Y = PY + 310
text(PX + 20, EX_Y, PW - 40, 16, "Ejemplo:",
     size=12, color="#89b4fa", align="left")
code_box(PX + 20, EX_Y + 22, PW - 40, 96, [
    "SELECT e.id, e.status, e.s3_pdf_key,",
    "       COUNT(a.id) AS artifact_count",
    "  FROM experiments e",
    "  LEFT JOIN artifacts a ON a.experiment_id = e.id",
    " WHERE e.status = 'analyzed'",
    " GROUP BY e.id;",
])


# ╔════════════════════════════════════════════════════════════════════╗
# ║ MINIO (top-right)                                                  ║
# ╚════════════════════════════════════════════════════════════════════╝
MX, MY = 760, 100
MW, MH = 660, 440
card(MX, MY, MW, MH, "#f9e2af", "#3d2800")

text(MX + 20, MY + 16, MW - 40, 24, "📦  MinIO (S3-compatible)",
     size=20, color="#f9e2af", align="left")
text(MX + 20, MY + 44, MW - 40, 16,
     "Object store   ·   pares  clave → bytes",
     size=12, color="#9399b2", align="left")

text(MX + 20, MY + 72, MW - 40, 16,
     "Qué guarda:  los blobs grandes que no caben (o no quieres) en SQL. "
     "Es la 'memoria larga'.",
     size=12, color="#cdd6f4", align="left")

text(MX + 20, MY + 100, MW - 40, 18, "Estructura de keys:",
     size=13, color="#f9e2af", align="left")

KEYS = [
    ("experiments/{id}/events.json",  "log completo de eventos (Sim Engine)"),
    ("experiments/{id}/replay.json",  "estado del grid por step (UI animación)"),
    ("experiments/{id}/tracker.json", "output del Tracker"),
    ("experiments/{id}/analyst.json", "output del Analyst"),
    ("experiments/{id}/charts/*.png", "gráficos matplotlib"),
    ("experiments/{id}/report.tex",   "fuente LaTeX del Reporter"),
    ("experiments/{id}/report.pdf",   "PDF final (tectonic)"),
    ("models/{model_id}.py",          "código .py de modelos Fase 1"),
]
for i, (key, desc) in enumerate(KEYS):
    y = MY + 124 + i * 22
    text(MX + 30, y, 280, 16, key,
         size=11, color="#fab387", align="left")
    text(MX + 320, y, MW - 340, 16, desc,
         size=11, color="#cdd6f4", align="left")

# Pattern note
PAT_Y = MY + 310
text(MX + 20, PAT_Y, MW - 40, 16, "Patrón:",
     size=12, color="#f9e2af", align="left")
code_box(MX + 20, PAT_Y + 22, MW - 40, 96, [
    "# Postgres tiene el puntero, MinIO tiene el contenido",
    "experiments.s3_pdf_key = 'experiments/abc/report.pdf'",
    "                              ↓",
    "                       MinIO bucket simlab/",
    "                       └── experiments/abc/report.pdf  (bytes)",
    "",
])


# ╔════════════════════════════════════════════════════════════════════╗
# ║ QDRANT (bottom-left)                                               ║
# ╚════════════════════════════════════════════════════════════════════╝
QX, QY = 60, 580
QW, QH = 660, 470
card(QX, QY, QW, QH, "#f38ba8", "#3b1528")

text(QX + 20, QY + 16, QW - 40, 24, "🔍  Qdrant",
     size=20, color="#f38ba8", align="left")
text(QX + 20, QY + 44, QW - 40, 16,
     "Base de datos vectorial   ·   búsqueda por SIMILITUD semántica",
     size=12, color="#9399b2", align="left")

text(QX + 20, QY + 72, QW - 40, 16,
     "La intuición:  guarda textos como vectores. Pregunta 'qué se parece a esto'.",
     size=12, color="#cdd6f4", align="left")
text(QX + 20, QY + 90, QW - 40, 16,
     "No busca palabras exactas — busca SIGNIFICADO.",
     size=12, color="#cdd6f4", align="left")

# Two collections
text(QX + 20, QY + 120, QW - 40, 18, "Colecciones:",
     size=13, color="#f38ba8", align="left")

text(QX + 30, QY + 144, QW - 60, 16,
     "• memories_dense    1024 dims (Voyage-3 embed)   ·   distancia COSINE",
     size=11, color="#cdd6f4", align="left")
text(QX + 30, QY + 162, QW - 60, 16,
     "• memories_sparse  vector disperso BM25 (IDF nativo)   ·   match por palabras clave",
     size=11, color="#cdd6f4", align="left")

text(QX + 20, QY + 188, QW - 40, 16,
     "Hibrido: dense (significado) + sparse (palabras) → fusionados con RRF.",
     size=11, color="#fab387", align="left")

# Visual: what a point looks like
text(QX + 20, QY + 216, QW - 40, 16,
     "Anatomía de un punto:",
     size=12, color="#f38ba8", align="left")
code_box(QX + 20, QY + 238, QW - 40, 110, [
    "id:       uuid",
    "vector:   { dense:  [0.23, -0.45, 0.91, ...]      ← 1024 floats }",
    "          { sparse: {'hunger': 4.2, 'decide': 3.8, ...}        }",
    "payload:  { source_kind: 'simulation_observation',",
    "            paradigm: 'homeostatic',",
    "            content: 'agente comió tras energía<30%',",
    "            run_id, created_at, ... }",
])

# Query example
text(QX + 20, QY + 360, QW - 40, 16, "Ejemplo de búsqueda:",
     size=12, color="#f38ba8", align="left")
code_box(QX + 20, QY + 382, QW - 40, 78, [
    "query = 'cómo reaccionan los agentes al hambre'",
    "  → embed con Voyage-3 → vector de 1024 dims",
    "  → Qdrant devuelve los 10 puntos MÁS CERCANOS por coseno",
    "  → cada uno con score 0.0-1.0 y payload con el texto original",
])


# ╔════════════════════════════════════════════════════════════════════╗
# ║ NEO4J (bottom-right)                                               ║
# ╚════════════════════════════════════════════════════════════════════╝
NX, NY = 760, 580
NW, NH = 660, 470
card(NX, NY, NW, NH, "#a6e3a1", "#0d2818")

text(NX + 20, NY + 16, NW - 40, 24, "🕸  Neo4j",
     size=20, color="#a6e3a1", align="left")
text(NX + 20, NY + 44, NW - 40, 16,
     "Base de datos de grafos   ·   nodos + aristas tipadas",
     size=12, color="#9399b2", align="left")

text(NX + 20, NY + 72, NW - 40, 16,
     "La intuición:  modelar RELACIONES, no solo datos. Tipo Wikipedia interna.",
     size=12, color="#cdd6f4", align="left")
text(NX + 20, NY + 90, NW - 40, 16,
     "Permite 'caminar' el grafo: 'qué papers fundamentan este paradigma'.",
     size=12, color="#cdd6f4", align="left")

# Node labels
text(NX + 20, NY + 120, NW - 40, 18, "Tipos de nodos (labels):",
     size=13, color="#a6e3a1", align="left")
NODES = [
    "Paradigm  ·  Postulate  ·  Formulation  ·  Model",
    "Variable  ·  Equation  ·  Parameter  ·  BrainRegion",
    "Author  ·  Paper",
    "Reflection  ·  RollupReflection  (memorias agregadas)",
]
for i, line in enumerate(NODES):
    text(NX + 30, NY + 144 + i * 18, NW - 60, 16, "• " + line,
         size=11, color="#cdd6f4", align="left")

# Edge types
text(NX + 20, NY + 226, NW - 40, 18, "Tipos de aristas:",
     size=13, color="#a6e3a1", align="left")
text(NX + 30, NY + 250, NW - 60, 16,
     "AUTHORED · CITES · SUPPORTS · CONTRADICTS · EXTENDS",
     size=11, color="#cdd6f4", align="left")
text(NX + 30, NY + 268, NW - 60, 16,
     "DERIVES_FROM · IMPLEMENTS · USES_EQUATION · BELONGS_TO · MEASURES · MODULATES",
     size=11, color="#cdd6f4", align="left")

# Mini graph illustration (text-based)
text(NX + 20, NY + 296, NW - 40, 16,
     "Ejemplo de subgrafo:",
     size=12, color="#a6e3a1", align="left")
code_box(NX + 20, NY + 318, NW - 40, 70, [
    "(Hull:Author)─AUTHORED→(Hull1943:Paper)─PROPOSES→(Homeostatic:Paradigm)",
    "                                                          │",
    "                                                      SUPPORTS",
    "                                                          ↓",
    "                                              (drive_reduction:Postulate)",
])

# Cypher query example
text(NX + 20, NY + 398, NW - 40, 16,
     "Ejemplo Cypher:",
     size=12, color="#a6e3a1", align="left")
code_box(NX + 20, NY + 420, NW - 40, 42, [
    "MATCH (p:Paradigm {slug:'homeostatic'})-[:SUPPORTS]->(po:Postulate)",
    "RETURN po.id, po.statement",
])


# ── Legend at the bottom ─────────────────────────────────────────────
LGY = 1075
text(60, LGY, 1360, 16,
     "Regla mental:   Postgres = 'el qué + dónde' (metadatos, joins, statuses)   "
     "·   MinIO = 'el contenido' (blobs, JSONs, PDFs)",
     size=12, color="#9399b2", align="left")
text(60, LGY + 22, 1360, 16,
     "                  Qdrant = 'qué se parece a esto' (búsqueda semántica)        "
     "·   Neo4j = 'qué está conectado con qué' (relaciones)",
     size=12, color="#9399b2", align="left")
text(60, LGY + 44, 1360, 16,
     "Los 4 conviven:  pipeline_memories vive en Postgres como source-of-truth, "
     "indexada en Qdrant para búsqueda y en Neo4j para relaciones entre conceptos.",
     size=12, color="#9399b2", align="left")


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

with open("storage_layer.excalidraw", "w") as f:
    json.dump(diagram, f, indent=2)
print(f"Written {len(elements)} elements")
