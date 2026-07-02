# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS base
ARG PNPM_VERSION=10.17.1
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"

# Keep the package manager setup in one reusable stage so every later stage
# uses the same pinned pnpm binary.
FROM base AS pnpm
RUN --mount=type=cache,id=find-npm-cache,target=/root/.npm \
    npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm install --global pnpm@${PNPM_VERSION} \
    && pnpm config set store-dir /pnpm/store

# Install dependencies only when needed
FROM pnpm AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN --mount=type=cache,id=find-pnpm-store,target=/pnpm/store \
    pnpm fetch

COPY package.json pnpm-workspace.yaml ./
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

# NEXT_PUBLIC_* values are inlined into the client bundle at build time, so they
# must be present here — setting them only at container runtime has no effect on
# already-built JS. Defaults match the docker-compose port mapping (MinIO on
# 9200, API on 8000). Override per-deployment with --build-arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_MINIO_URL=http://localhost:9200
ARG NEXT_PUBLIC_MINIO_BUCKET=images
ARG NEXT_PUBLIC_MAX_BULK_FILES=200
ARG NEXT_PUBLIC_MAX_UPLOAD_SIZE_MB=50
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_MINIO_URL=$NEXT_PUBLIC_MINIO_URL
ENV NEXT_PUBLIC_MINIO_BUCKET=$NEXT_PUBLIC_MINIO_BUCKET
ENV NEXT_PUBLIC_MAX_BULK_FILES=$NEXT_PUBLIC_MAX_BULK_FILES
ENV NEXT_PUBLIC_MAX_UPLOAD_SIZE_MB=$NEXT_PUBLIC_MAX_UPLOAD_SIZE_MB

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
