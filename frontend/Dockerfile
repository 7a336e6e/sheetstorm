# Base image pinned by multi-arch index digest (Dependabot "docker" updates it).
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app

# Supply-chain hardening (see assets/docs/supply-chain.md):
#  - lockfile-only install (npm ci); the lockfile is REQUIRED, never `npm install`
#  - lifecycle scripts disabled (.npmrc ignore-scripts=true + explicit flag).
#    No dependency currently needs one: @next/swc, sharp (@img/*) and
#    unrs-resolver ship prebuilt binaries as optionalDependencies. If one ever
#    does, allowlist it explicitly here with `npm rebuild <pkg>` - never
#    re-enable scripts globally.
#  - no secrets in this stage: only package manifests are copied.
COPY package.json package-lock.json .npmrc ./
RUN npm ci --ignore-scripts --legacy-peer-deps --no-fund

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN mkdir -p /app/public

# Build arguments for environment variables
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY

ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY

# Build the application
RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built files
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
