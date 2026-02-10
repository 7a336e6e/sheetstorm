FROM postgres:16-alpine

# Copy initialization scripts
COPY init/ /docker-entrypoint-initdb.d/

# Set permissions
RUN chmod -R 755 /docker-entrypoint-initdb.d/

EXPOSE 5432
