# Phase 2 backend deployment

Railway service settings:

- Root Directory: `/`
- Config File Path: `/phase2-juan/backend/railway.json`
- Dockerfile Path: `phase2-juan/backend/Dockerfile`

The backend must build from the repository root because `simlab` depends on the
top-level `shared/` package. Setting Railway Root Directory to
`/phase2-juan/backend` would make Docker unable to copy `shared/`.
