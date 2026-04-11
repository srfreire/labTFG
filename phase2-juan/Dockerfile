# Phase 2 server — build from repo root: docker build -f phase2-juan/Dockerfile .
# ── Tectonic (LaTeX→PDF compiler) ────────────────────────
FROM rust:slim AS tectonic-builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends pkg-config libssl-dev libfontconfig1-dev && \
    cargo install tectonic && \
    strip /usr/local/cargo/bin/tectonic && \
    rm -rf /var/lib/apt/lists/*

# ── Python dependencies ─────────────────────────────────
FROM python:3.12-slim AS builder

RUN pip install uv

WORKDIR /app

# Copy shared package first (dependency layer)
COPY shared/ /app/shared/

# Copy Phase 2 source
COPY phase2-juan/ /app/phase2-juan/

WORKDIR /app/phase2-juan
RUN uv sync --frozen --no-dev

# ── Runtime ──────────────────────────────────────────────
FROM python:3.12-slim

# Runtime deps for tectonic
RUN apt-get update && \
    apt-get install -y --no-install-recommends libfontconfig1 libssl3 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=tectonic-builder /usr/local/cargo/bin/tectonic /usr/local/bin/tectonic

WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/phase2-juan/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "simlab.api:app", "--host", "0.0.0.0", "--port", "8000"]
