# Test-only OpenID Connect provider for the e2e stack (ci/compose.e2e.yml).
# Standard library only; same digest-pinned base image as the backend.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY server.py /mock/server.py
USER nobody
EXPOSE 9000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=2)"
CMD ["python", "/mock/server.py"]
