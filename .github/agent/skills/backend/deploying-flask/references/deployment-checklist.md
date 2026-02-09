---
name: Deployment Checklist
description: Pre-deployment verification checklist for Flask applications to ensure production readiness.
---

# Deployment Checklist

Use this checklist before every production deployment. All items must pass before proceeding.

## Configuration

- [ ] `DEBUG=False` in production config
- [ ] `TESTING=False` in production config
- [ ] `SECRET_KEY` is a cryptographically random value (not the default)
- [ ] All secrets loaded from environment variables
- [ ] No hardcoded credentials in source code
- [ ] `.env` file is NOT deployed (only `.env.example` in repo)

## Database

- [ ] Database migrations applied successfully
- [ ] Database connection string uses production credentials
- [ ] Connection pooling configured appropriately
- [ ] Database backups verified and recent
- [ ] Read replicas configured (if applicable)

## Security

- [ ] CORS configured for production origins only (no wildcards)
- [ ] Rate limiting enabled on all endpoints
- [ ] Rate limits stricter on authentication endpoints
- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] HSTS header configured with appropriate max-age
- [ ] Security headers present:
  - [ ] `X-Content-Type-Options: nosniff`
  - [ ] `X-Frame-Options: DENY` or `SAMEORIGIN`
  - [ ] `Content-Security-Policy` configured
  - [ ] `Referrer-Policy` configured
- [ ] CSRF protection enabled for form submissions
- [ ] Session cookies have `Secure`, `HttpOnly`, `SameSite` flags

## Application Server

- [ ] Gunicorn (or uWSGI) configured as WSGI server
- [ ] Flask development server NOT used in production
- [ ] Worker count set appropriately: `(2 * CPU cores) + 1`
- [ ] Worker timeout configured (default 30s may need adjustment)
- [ ] Graceful shutdown configured

## Reverse Proxy

- [ ] Nginx (or similar) configured as reverse proxy
- [ ] Static files served by Nginx, not Flask
- [ ] SSL/TLS certificate valid and not expiring soon
- [ ] Gzip compression enabled for text responses
- [ ] Request size limits configured
- [ ] Proxy headers forwarded correctly (`X-Forwarded-For`, `X-Forwarded-Proto`)

## Containerization (if using Docker)

- [ ] Multi-stage build used to minimize image size
- [ ] Application runs as non-root user
- [ ] No secrets baked into the image
- [ ] Health check endpoint configured in Dockerfile
- [ ] Image tagged with version, not just `latest`

## Logging & Monitoring

- [ ] Structured logging configured (JSON format)
- [ ] No sensitive data logged (passwords, tokens, PII)
- [ ] Log level set appropriately (INFO or WARNING in production)
- [ ] Error tracking service connected (Sentry, Rollbar, etc.)
- [ ] Application metrics exposed (Prometheus, StatsD, etc.)
- [ ] Alerts configured for error rate spikes

## Health & Availability

- [ ] Health check endpoint (`/health` or `/api/health`) responds with 200
- [ ] Health check verifies database connectivity
- [ ] Readiness probe configured (for Kubernetes/orchestrators)
- [ ] Liveness probe configured (for Kubernetes/orchestrators)

## Performance

- [ ] Response caching configured where appropriate
- [ ] Database query performance verified (no N+1, slow queries)
- [ ] Static assets have cache headers
- [ ] API responses compressed

## Rollback Plan

- [ ] Previous version tagged and available for rollback
- [ ] Database migration has a working downgrade path
- [ ] Rollback procedure documented and tested
- [ ] Team knows the rollback command/process

---

## Quick Verification Commands

```bash
# Check if debug mode is disabled
curl -I https://your-app.com/api/health | grep -i "server"
# Should NOT reveal Flask version or debug info

# Verify HTTPS redirect
curl -I http://your-app.com
# Should return 301/302 redirect to https://

# Check security headers
curl -I https://your-app.com | grep -iE "(strict-transport|x-frame|x-content-type|content-security)"

# Health check
curl https://your-app.com/api/health
# Should return {"status": "healthy"}
```
