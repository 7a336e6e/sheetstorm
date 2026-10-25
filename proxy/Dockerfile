# Base image pinned by multi-arch index digest (bumped by hand, see
# assets/docs/supply-chain.md section 6).
FROM nginx:1.31-alpine@sha256:a3554c0d0b48177b1413c26e01f695334428020d9df01243fbae3e11cfd17417

RUN rm /etc/nginx/conf.d/default.conf

# Renders /etc/nginx/realip.conf from TRUSTED_PROXY_CIDRS / REAL_IP_HEADER at
# container start (official image runs /docker-entrypoint.d/*.sh).
COPY docker-entrypoint-realip.sh /docker-entrypoint.d/40-sheetstorm-realip.sh
RUN chmod 755 /docker-entrypoint.d/40-sheetstorm-realip.sh \
    && /docker-entrypoint.d/40-sheetstorm-realip.sh
COPY nginx.conf /etc/nginx/conf.d/sheetstorm.conf

EXPOSE 80
