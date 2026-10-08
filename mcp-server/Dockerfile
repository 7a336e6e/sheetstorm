# =============================================================================
# SheetStorm MCP Server — Multi-stage Docker build
# =============================================================================
# Build:  docker build -t sheetstorm-mcp ./mcp-server
# Run:    docker run --rm -p 8811:8811 \
#           -e SHEETSTORM_API_URL=http://backend:5000/api/v1 \
#           -e MCP_ISSUER_URL=https://mcp.example.com \
#           -e REDIS_URL=redis://redis:6379/0 sheetstorm-mcp
#
# The remote (sse) transport authenticates every user through the browser
# OAuth flow; it never uses SHEETSTORM_USERNAME/PASSWORD/API_TOKEN.
# All Python dependencies are installed hash-locked from requirements.lock
# (compiled from constraints.txt by scripts/lock-python.sh); the build backend
# from build-requirements.lock. See assets/docs/supply-chain.md.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — install deps + build wheel
# ---------------------------------------------------------------------------
# Base image pinned by multi-arch index digest (Dependabot "docker" updates it);
# same base as the backend image.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder

WORKDIR /build

# Hash-locked build backend (hatchling), so --no-build-isolation below never
# fetches an unpinned package. The --no-index step fails the build if
# build-requirements.txt was edited without regenerating the lock.
COPY build-requirements.txt build-requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r build-requirements.lock \
    && pip install --no-cache-dir --no-index --no-deps -r build-requirements.txt

# Build only our own wheel - dependencies come from requirements.lock at runtime
COPY . .
RUN pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir /wheels .

# ---------------------------------------------------------------------------
# Stage 2: Runtime — minimal image
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

LABEL maintainer="SheetStorm Team"
LABEL description="MCP server for SheetStorm incident response platform"
LABEL org.opencontainers.image.source="https://github.com/7a336e6e/sheetstorm"

# Security: run as non-root
RUN groupadd -r mcp && useradd -r -g mcp -d /app -s /sbin/nologin mcp

WORKDIR /app

# Hash-locked dependencies (wheels only, no resolver), then our wheel without
# re-resolving. The --no-index step fails the build if constraints.txt was
# edited without regenerating requirements.lock; pip check proves the locked
# set satisfies the package's declared dependencies.
COPY constraints.txt requirements.lock /tmp/deps/
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r /tmp/deps/requirements.lock \
    && pip install --no-cache-dir --no-index --no-deps -r /tmp/deps/constraints.txt \
    && pip install --no-cache-dir --no-index --no-deps /wheels/*.whl \
    && pip check \
    && rm -rf /wheels /tmp/deps

# Copy .env.example as reference (actual config via env vars)
COPY .env.example /app/.env.example

# Per-user artifact sandboxes live below ARTIFACT_DIR (created 0700)
RUN mkdir -p /app/artifacts && chown mcp:mcp /app/artifacts && chmod 700 /app/artifacts

# Switch to non-root user
USER mcp

# Default environment variables
ENV SHEETSTORM_API_URL=http://backend:5000/api/v1 \
    MCP_TRANSPORT=sse \
    ARTIFACT_DIR=/app/artifacts \
    SSE_PORT=8811 \
    LOG_LEVEL=INFO \
    HTTP_TIMEOUT=30 \
    HTTP_MAX_RETRIES=2

# Expose SSE port (only used when MCP_TRANSPORT=sse)
EXPOSE 8811

# Health check — verify the Python package is importable
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from sheetstorm_mcp.server import mcp; print('ok')" || exit 1

ENTRYPOINT ["sheetstorm-mcp"]
