# syntax=docker/dockerfile:1.10
# Build context: repo root (not apps/frontend) — see docker-compose.yml
FROM node:20-alpine AS base
ENV PNPM_HOME="/pnpm" \
    PATH="$PNPM_HOME:$PATH" \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable

# ── Install all workspace deps ────────────────────────────────────────────────
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/frontend/package.json ./apps/frontend/
COPY packages/shared/package.json ./packages/shared/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── Development: node_modules baked in, src mounted via volume ────────────────
FROM base AS development
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json pnpm-workspace.yaml ./
COPY apps/frontend/package.json ./apps/frontend/
COPY packages/shared/package.json ./packages/shared/
COPY apps/frontend ./apps/frontend
COPY packages ./packages
WORKDIR /repo/apps/frontend
EXPOSE 3000
CMD ["pnpm", "dev", "--hostname", "0.0.0.0"]

# ── Production builder ────────────────────────────────────────────────────────
FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
RUN pnpm --filter frontend build

# ── Production runtime: Next.js standalone ────────────────────────────────────
FROM node:20-alpine AS production
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /repo/apps/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/apps/frontend/.next/static ./apps/frontend/.next/static
COPY --from=builder --chown=nextjs:nodejs /repo/apps/frontend/public ./apps/frontend/public
USER nextjs
EXPOSE 3000
CMD ["node", "apps/frontend/server.js"]
