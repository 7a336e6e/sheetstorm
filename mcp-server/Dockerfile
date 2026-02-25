# =============================================================================
# SheetStorm MCP Server — Multi-stage Docker build
# =============================================================================
# Build:  docker build -t sheetstorm-mcp ./mcp-server
# Run:    docker run --rm -e SHEETSTORM_API_URL=http://backend:5000/api/v1 \
#           -e SHEETSTORM_USERNAME=admin@sheetstorm.local \
#           -e SHEETSTORM_PASSWORD=changeme sheetstorm-mcp
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — install deps + build wheel
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir hatchling

# Copy only dependency-defining files first (cache layer)
COPY pyproject.toml README.md ./
COPY sheetstorm_mcp/__init__.py sheetstorm_mcp/__init__.py

# Build wheel
COPY . .
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

# ---------------------------------------------------------------------------
# Stage 2: Runtime — minimal image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL maintainer="SheetStorm Team"
LABEL description="MCP server for SheetStorm incident response platform"
LABEL org.opencontainers.image.source="https://github.com/7a336e6e/sheetstorm"

# Security: run as non-root
RUN groupadd -r mcp && useradd -r -g mcp -d /app -s /sbin/nologin mcp

WORKDIR /app

# Install the wheel from build stage
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Copy .env.example as reference (actual config via env vars)
COPY .env.example /app/.env.example

# Switch to non-root user
USER mcp

# Default environment variables
ENV SHEETSTORM_API_URL=http://backend:5000/api/v1 \
    MCP_TRANSPORT=sse \
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
