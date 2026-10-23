# Base image pinned by multi-arch index digest (Dependabot "docker" updates it).
FROM postgres:16-alpine@sha256:f4610795587492cd4fb887c2dc3de301b813278bb6f616992061141b5f15ac36

# Copy initialization scripts
COPY init/ /docker-entrypoint-initdb.d/

# Set permissions
RUN chmod -R 755 /docker-entrypoint-initdb.d/

EXPOSE 5432
