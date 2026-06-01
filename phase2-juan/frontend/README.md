# Phase 2 frontend deployment

Railway service settings:

- Root Directory: `/phase2-juan/frontend`
- Config File Path: `/phase2-juan/frontend/railway.json`
- Dockerfile Path: `Dockerfile`

Set `BACKEND_HOST` and `BACKEND_PORT` in Railway to point nginx at the Phase 2
backend service. For local Docker Compose, the defaults are `phase2-server:8000`.
