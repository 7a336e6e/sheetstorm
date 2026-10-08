# Base image pinned by multi-arch index digest (Dependabot "docker" updates it).
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime

# Runtime libraries only. Every Python dependency installs from a prebuilt
# wheel (--only-binary=:all: below), so no compiler or -dev headers are needed.
# WeasyPrint (PDF reports/exports) dlopens pango/pangoft2/harfbuzz/fontconfig;
# cairo/gdk-pixbuf are not used by WeasyPrint >= 53 but are kept as small
# runtime libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libharfbuzz-subset0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    fonts-liberation \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

# Hash-locked install (assets/docs/supply-chain.md): every package and version
# comes from requirements.lock with its sha256, wheels only, no resolver.
# The second command fails the build if requirements.txt was edited without
# regenerating the lock (scripts/lock-python.sh) - the pip analogue of `npm ci`.
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r requirements.lock \
    && pip install --no-cache-dir --no-index --no-deps -r requirements.txt \
    && pip check

# Copy application code
COPY . .

# Make entrypoint executable, create the local evidence-storage dir (mounted as
# a named volume in docker-compose so evidence survives container recreation),
# and set ownership
RUN chmod +x /app/entrypoint.sh && mkdir -p /app/artifacts \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 5000

# Entrypoint applies DB migrations, then runs the server command.
# Use eventlet for Flask-SocketIO via wsgi.py
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "wsgi.py"]

# ---------------------------------------------------------------------------
# Test image (backend/tests/run_in_docker.sh builds --target test): the runtime
# image plus the hash-locked test-only deps from requirements-dev.lock.
# ---------------------------------------------------------------------------
FROM runtime AS test
USER root
RUN pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r requirements-dev.lock \
    && pip install --no-cache-dir --no-index --no-deps -r requirements-dev.txt \
    && pip check
USER appuser

# Default target: the production runtime image (no test dependencies).
FROM runtime
