# Phase 1 server — build from repo root: docker build -f phase1-pablo/Dockerfile .
# ── Builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN pip install uv

WORKDIR /app

# Copy shared package first (dependency layer)
COPY shared/ /app/shared/

# Copy Phase 1 source
COPY phase1-pablo/ /app/phase1-pablo/

WORKDIR /app/phase1-pablo
RUN uv sync --frozen --no-dev

# ── Runtime ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app /app

ENV PATH="/app/phase1-pablo/.venv/bin:$PATH"

EXPOSE 8001
CMD ["uvicorn", "decisionlab.server:app", "--host", "0.0.0.0", "--port", "8001"]
