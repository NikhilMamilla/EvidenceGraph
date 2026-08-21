# =============================================================================
# EvidenceGraph Frontend — Dockerfile
# Build with Vite, serve with nginx
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --frozen-lockfile

COPY . .

# VITE_API_BASE_URL is injected at build time via docker-compose environment
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: production — nginx
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
