---
id: P4-003
title: Create Dockerfile for Phase 2 web frontend
status: done
kind: strike
phase: 4
heat: containers
priority: 1
blocked_by: [P3-003]
created: 2026-04-11
updated: 2026-04-11
---

# P4-003: Create Dockerfile for Phase 2 web frontend

## Objective
Containerize the Phase 2 React frontend with nginx serving static files and proxying WebSocket/API to the Phase 2 server.

## Requirements
- Multi-stage Dockerfile at `phase2-juan/web/Dockerfile`
- Build stage:
  - Base: `node:22-slim`
  - Install pnpm via corepack
  - Copy `package.json`, `pnpm-lock.yaml`, install dependencies
  - Copy source, run `pnpm build` (Vite production build)
- Serve stage:
  - Base: `nginx:alpine`
  - Copy built static files from build stage to `/usr/share/nginx/html`
  - Copy custom nginx config
- Nginx config (`phase2-juan/web/nginx.conf`):
  - Serve static files from `/`
  - Proxy `/ws` → `http://phase2-server:8000/ws` (WebSocket upgrade headers)
  - Proxy `/api` → `http://phase2-server:8000/api`
  - SPA fallback: all non-file routes → `index.html`
- Expose port 80
- `.dockerignore` (exclude `node_modules/`, `dist/`, `.env`)

## Acceptance Criteria
- [x] `docker build -t labtfg-web phase2-juan/web/` builds without errors
- [x] Container serves the React app on port 80
- [x] Nginx proxies WebSocket connections to Phase 2 server
- [x] SPA routing works (direct URL access to any route serves index.html)
- [x] Static assets (JS, CSS) served with correct content types

## Files Likely Affected
- `phase2-juan/web/Dockerfile` — new file
- `phase2-juan/web/nginx.conf` — new file
- `phase2-juan/web/.dockerignore` — new file

## Context
Phase spec: `docs/specs/infrastructure/phase-4-containerization.md`
General spec: `docs/specs/infrastructure/general.md`
Heat: `containers`

## Completion Summary

**Commit:** `bf79b25` — `feat[infra]: add Dockerfiles for all services (P4-001, P4-002, P4-003)`

### What was built
- Multi-stage Dockerfile for web frontend (node:22-slim build stage with pnpm, nginx:alpine serve stage)
- Nginx config with WebSocket proxy to phase2-server, API proxy, and SPA fallback
- .dockerignore for web directory

### Files created
- `phase2-juan/web/Dockerfile` — multi-stage build
- `phase2-juan/web/nginx.conf` — proxy + SPA config
- `phase2-juan/web/.dockerignore` — node_modules, dist, .env
