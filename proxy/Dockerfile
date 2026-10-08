# Base image pinned by multi-arch index digest (Dependabot "docker" updates it).
FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236

RUN rm /etc/nginx/conf.d/default.conf

# Renders /etc/nginx/realip.conf from TRUSTED_PROXY_CIDRS / REAL_IP_HEADER at
# container start (official image runs /docker-entrypoint.d/*.sh).
COPY docker-entrypoint-realip.sh /docker-entrypoint.d/40-sheetstorm-realip.sh
RUN chmod 755 /docker-entrypoint.d/40-sheetstorm-realip.sh \
    && /docker-entrypoint.d/40-sheetstorm-realip.sh
COPY nginx.conf /etc/nginx/conf.d/sheetstorm.conf

EXPOSE 80
