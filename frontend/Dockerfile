# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS base
ARG PNPM_VERSION=10.17.1
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

# Keep the package manager setup in one reusable stage so every later stage
# uses the same pinned pnpm binary.
FROM base AS pnpm
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate \
    && pnpm config set store-dir /pnpm/store

# Install dependencies only when needed
FROM pnpm AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY pnpm-lock.yaml* ./
RUN --mount=type=cache,id=find-pnpm-store,target=/pnpm/store \
    pnpm fetch

COPY package.json ./
RUN --mount=type=cache,id=find-pnpm-store,target=/pnpm/store \
    pnpm install --offline --frozen-lockfile

# Development image
FROM pnpm AS development
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 3000
ENV PORT 3000

CMD ["pnpm", "run", "dev"]

# Production build
FROM pnpm AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED 1
ENV NEXT_OUTPUT standalone

RUN pnpm run build

# Production image
FROM base AS production
WORKDIR /app

ENV NODE_ENV production
ENV NEXT_TELEMETRY_DISABLED 1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]
