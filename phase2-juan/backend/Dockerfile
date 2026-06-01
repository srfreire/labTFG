# Phase 2 backend — build from repo root:
# docker build -f phase2-juan/backend/Dockerfile .
# ── Tectonic (LaTeX→PDF compiler) ────────────────────────
FROM rust:slim AS tectonic-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libssl-dev \
        libfontconfig1-dev \
        libgraphite2-dev \
        libharfbuzz-dev \
        libicu-dev && \
    cargo install tectonic && \
    strip /usr/local/cargo/bin/tectonic && \
    rm -rf /var/lib/apt/lists/*

# ── Python dependencies ─────────────────────────────────
FROM python:3.12-slim AS builder

ENV UV_PYTHON_DOWNLOADS=never

RUN pip install uv

WORKDIR /app

# Copy shared package first (dependency layer)
COPY shared/ /app/shared/

# Copy Phase 1 modules used by Phase 2 recall/retrieval enrichment.
COPY phase1-pablo/src/ /app/phase1-pablo/src/

# Copy Phase 2 source
COPY phase2-juan/ /app/phase2-juan/

WORKDIR /app/phase2-juan
RUN uv sync --frozen --no-dev --python /usr/local/bin/python

# ── Runtime ──────────────────────────────────────────────
FROM python:3.12-slim

# Runtime deps for tectonic
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libfontconfig1 \
        libgraphite2-3 \
        libharfbuzz0b \
        libicu76 \
        libssl3 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=tectonic-builder /usr/local/cargo/bin/tectonic /usr/local/bin/tectonic

WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/phase2-juan/.venv/bin:$PATH" \
    PYTHONPATH="/app/phase1-pablo/src"

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "simlab.api:app", "--host", "0.0.0.0", "--port", "8000"]
