# Shield AI — Next.js frontend image (Cloud Run production)
#
# The frontend proxies all backend calls through /api/backend/* (Next.js API route).
# Set BACKEND_URL at runtime (Cloud Run env var) — no build-arg needed.
#
# Multi-stage build:
#   1. deps    — install node_modules (cached layer)
#   2. builder — next build with standalone output
#   3. runner  — minimal alpine image (~150 MB vs ~1 GB full install)

# ── Stage 1: install deps ──────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app

COPY frontend-next/package.json frontend-next/package-lock.json ./
RUN npm ci

# ── Stage 2: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY frontend-next/ .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# ── Stage 3: production runner ────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1

# BACKEND_URL is read at runtime by the /api/backend proxy route (server-side only).
# Cloud Run injects this via --set-env-vars. Default allows local dev to work.
ENV BACKEND_URL=http://localhost:8000

# Non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

COPY --from=builder /app/public                    ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static     ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
