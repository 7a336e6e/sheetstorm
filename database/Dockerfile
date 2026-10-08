# Base image pinned by multi-arch index digest (Dependabot "docker" updates it).
FROM postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea

# Copy initialization scripts
COPY init/ /docker-entrypoint-initdb.d/

# Set permissions
RUN chmod -R 755 /docker-entrypoint-initdb.d/

EXPOSE 5432
