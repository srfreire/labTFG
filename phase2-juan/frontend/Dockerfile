# Phase 2 frontend — build context is phase2-juan/frontend/
# ── Build ────────────────────────────────────────────────
FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Serve ────────────────────────────────────────────────
FROM nginx:alpine

# Defaults match docker-compose service DNS so local runs keep working.
# Railway / other deployments override BACKEND_HOST via the environment.
ENV PORT=80 \
    BACKEND_HOST=phase2-server \
    BACKEND_PORT=8000 \
    NGINX_ENVSUBST_FILTER="(PORT|BACKEND_HOST|BACKEND_PORT|NGINX_LOCAL_RESOLVERS)"

COPY --from=builder /app/dist /usr/share/nginx/html
# nginx-alpine's built-in entrypoint renders /etc/nginx/templates/*.template
# with envsubst into /etc/nginx/conf.d/ at container start.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Wrap the stock entrypoint so NGINX_LOCAL_RESOLVERS is populated from
# /etc/resolv.conf before envsubst runs — Railway needs this to proxy to
# *.railway.internal hostnames.
COPY docker-entrypoint.sh /labtfg-entrypoint.sh
RUN chmod +x /labtfg-entrypoint.sh
ENTRYPOINT ["/labtfg-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]

EXPOSE 80
